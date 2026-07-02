// Night loop — `opencanal-runner night run`.
// 밤 생산 루프(피벗 v2 — docs/DIRECTION.md): 큐 pull → 교정 드레인(Correct) → 팩 컨텍스트 →
// 카드별 생산(모든 판단에 policyId provenance) → 결과 보고. 계약층은 @opencanal/shared/night.
// 바깥으로 나가는 것은 없다 — 산출물은 아침 리뷰(승인 게이트)까지 보류된다.

import {
  nightQueueSchema,
  nightRunReportSchema,
  buildNightConstitution,
  parseNightBrainOutput,
  type NightQueue,
  type NightCorrection,
  type TaskCard,
  type JournalEntry,
  type ProducedArtifact,
  type TaskResult,
  type NightRunReport,
} from "@opencanal/shared";
import { loadConfig, type RunnerConfig } from "./config";
import { OpencrabClient } from "./sources/opencrab";
import { ClaudeAdapter } from "./brain/claude";
import { CodexAdapter } from "./brain/codex";
import type { BrainAdapter } from "./brain/adapter";

const DEFAULT_LIMIT = 3;

interface NightOptions {
  limit: number;
  dry: boolean;
}

function makeBrain(provider: string): BrainAdapter {
  if (provider === "codex") {
    console.warn("[brain] codex adapter is EXPERIMENTAL");
    return new CodexAdapter();
  }
  return new ClaudeAdapter();
}

function parseNightArgs(args: string[]): NightOptions {
  let limit = DEFAULT_LIMIT;
  let dry = false;
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--dry") dry = true;
    else if (a === "--limit") {
      const n = Number(args[++i]);
      if (Number.isFinite(n) && n > 0) limit = Math.floor(n);
    } else if (a.startsWith("--limit=")) {
      const n = Number(a.slice("--limit=".length));
      if (Number.isFinite(n) && n > 0) limit = Math.floor(n);
    }
  }
  return { limit, dry };
}

// ── 플랫폼 night HTTP (device-token auth) ──

async function platformFetch<T>(
  config: RunnerConfig,
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${config.platformUrl}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.deviceToken}`,
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${method} ${path} → ${res.status} ${text.slice(0, 200)}`);
  }
  // 일부 엔드포인트는 빈 바디를 반환할 수 있다.
  const raw = await res.text();
  return (raw ? JSON.parse(raw) : {}) as T;
}

const nowIso = () => new Date().toISOString();

function journal(
  kind: JournalEntry["kind"],
  text: string,
  extra?: { taskId?: string | null; policyId?: string | null }
): JournalEntry {
  return { at: nowIso(), kind, text, taskId: extra?.taskId ?? null, policyId: extra?.policyId ?? null };
}

// 카드의 두뇌 프롬프트 — brief + 밤 출력 계약(JSON). policyId는 [P:id]의 id.
function buildTaskPrompt(card: TaskCard): string {
  const originBits = [
    card.originNote ? `근거(왜 이 작업인가): ${card.originNote}` : null,
    card.originPolicyId ? `출처 정책: [P:${card.originPolicyId}]` : null,
  ].filter(Boolean);
  return `# 작업 카드: ${card.title}
${card.brief}
${originBits.length ? `\n${originBits.join("\n")}\n` : ""}
지금 이 카드를 소유자의 목소리와 판단으로 실물로 만들어라. 아침에 소유자가 승인/반려한다.

# 출력 계약 (반드시 아래 JSON 하나만 출력, 코드펜스/설명 금지)
{
  "title": "산출물 제목",
  "content": "산출물 본문 (마크다운)",
  "decisions": [{ "text": "이 판단을 왜 이렇게 했는지", "policyId": "인용한 정책 id 또는 null" }],
  "skipped": null
}
- 판단이 정책을 따르거나 정책에 의해 제약될 때, 그 정책 id를 policyId에 넣어라 (헌법의 [P:id]에서 id만).
- 레드 플래그와 충돌하면 생산하지 말고 "skipped": { "reason": "왜 건너뛰는가", "policyId": "위반될 뻔한 레드 플래그 id 또는 null" } 로 응답하라 (이때 title/content는 비워도 된다).
- 소유자에 대해 팩이 뒷받침하지 않는 사실을 지어내지 마라.`;
}

// 반려 교정 → 팩 재ingest 본문 (Correct 루프의 원료).
function correctionIngestBody(c: NightCorrection): { title: string; content: string } {
  const title = `아침 리뷰 반려 교정 — ${c.artifactTitle}`;
  const content = [
    `반려된 산출물: ${c.artifactTitle}`,
    c.taskTitle ? `작업 맥락: ${c.taskTitle}` : null,
    `반려 사유: ${c.reason}`,
    `리뷰 시각: ${c.reviewedAt}`,
    "",
    "이 교정을 향후 같은 종류의 판단에 반영하라.",
  ]
    .filter(Boolean)
    .join("\n");
  return { title, content };
}

// ─────────────────────────── night run ───────────────────────────

export async function cmdNightRun(args: string[]): Promise<void> {
  const opts = parseNightArgs(args);
  const config = loadConfig();

  if (!config.deviceToken) {
    console.error("먼저 `opencanal-runner login`으로 페어링하세요.");
    process.exit(1);
  }

  // 1) 큐 pull
  const rawQueue = await platformFetch<unknown>(config, "GET", "/api/night/queue");
  const queue: NightQueue = nightQueueSchema.parse(rawQueue);

  if (queue.tasks.length === 0 && queue.corrections.length === 0) {
    console.log("오늘 밤 할 일이 없다 — 큐가 비어 있습니다 (카드 0, 교정 0).");
    return;
  }

  const opencrab = config.opencrab?.token
    ? new OpencrabClient(config.opencrab.token, config.opencrab.mcpUrl)
    : null;

  const startedAt = nowIso();
  const journalLog: JournalEntry[] = [];
  const artifacts: ProducedArtifact[] = [];
  const taskResults: TaskResult[] = [];

  console.log(`OpenCanal Runner — night run${opts.dry ? " (dry)" : ""}`);
  console.log(`  agent: @${queue.agent.handle} (${queue.agent.displayName})`);
  console.log(`  큐: 카드 ${queue.tasks.length} · 교정 ${queue.corrections.length} · 정책 ${queue.policies.length}`);

  try {
    // 2) 교정 드레인 (Correct 루프)
    const acked: string[] = [];
    for (const c of queue.corrections) {
      if (!opencrab) {
        journalLog.push(
          journal("correction", `팩 미연결 — 교정 보류: ${c.artifactTitle} (사유: ${c.reason})`)
        );
        continue;
      }
      const { title, content } = correctionIngestBody(c);
      if (opts.dry) {
        journalLog.push(journal("correction", `[dry] 교정 재ingest 예정: ${c.artifactTitle}`));
        continue;
      }
      try {
        await opencrab.ingestText(title, content, false);
        acked.push(c.artifactId);
        journalLog.push(journal("correction", `교정 재ingest 완료: ${c.artifactTitle} — 팩에 반영`));
      } catch (err) {
        journalLog.push(
          journal(
            "correction",
            `교정 재ingest 실패(보류): ${c.artifactTitle} — ${err instanceof Error ? err.message : String(err)}`
          )
        );
      }
    }
    if (acked.length > 0 && !opts.dry) {
      await platformFetch(config, "POST", "/api/night/corrections/ack", { artifactIds: acked });
      console.log(`  교정 ack: ${acked.length}건`);
    }

    // 3) 팩 컨텍스트 (실패해도 진행)
    let personaBlock = "";
    if (opencrab) {
      const question = [
        ...queue.tasks.map((t) => t.title),
        ...queue.directives.map((d) => d.content),
      ].join(" · ");
      try {
        personaBlock = await opencrab.personaContext(
          question || queue.agent.displayName,
          5,
          config.opencrab?.workspaceId
        );
      } catch {
        personaBlock = "";
      }
    }

    // 4) 생산
    const system = buildNightConstitution({
      agentHandle: queue.agent.handle,
      agentDisplayName: queue.agent.displayName,
      ownerName: queue.ownerName,
      policies: queue.policies,
      directives: queue.directives,
      personaBlock,
    });
    const brain = makeBrain(config.brain.provider);

    const cards = queue.tasks.slice(0, opts.limit);
    for (const card of cards) {
      journalLog.push(
        journal("plan", `카드 착수: ${card.title} — 근거: ${card.originNote ?? card.originPolicyId ?? "(미기재)"}`, {
          taskId: card.id,
          policyId: card.originPolicyId,
        })
      );

      try {
        const raw = await brain.complete(system, buildTaskPrompt(card));
        const output = parseNightBrainOutput(raw, card.title);

        if (output.skipped) {
          taskResults.push({ taskId: card.id, status: "skipped", note: output.skipped.reason });
          journalLog.push(
            journal("decision", `건너뜀: ${card.title} — ${output.skipped.reason}`, {
              taskId: card.id,
              policyId: output.skipped.policyId,
            })
          );
          console.log(`  ⤫ ${card.title} — 건너뜀 (${output.skipped.reason})`);
          continue;
        }

        artifacts.push({ taskId: card.id, kind: "markdown", title: output.title, content: output.content });
        taskResults.push({ taskId: card.id, status: "produced" });
        for (const d of output.decisions) {
          journalLog.push(journal("decision", d.text, { taskId: card.id, policyId: d.policyId }));
        }
        journalLog.push(
          journal("produce", `${output.title} 생산, ${output.content.length}자`, { taskId: card.id })
        );
        console.log(`  ✓ ${output.title} (${output.content.length}자)`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        taskResults.push({ taskId: card.id, status: "failed", note: msg });
        journalLog.push(journal("note", `카드 실패: ${card.title} — ${msg}`, { taskId: card.id }));
        console.log(`  ✗ ${card.title} — 실패 (${msg})`);
      }
    }

    // 5) 보고
    const report: NightRunReport = nightRunReportSchema.parse({
      startedAt,
      finishedAt: nowIso(),
      status: "completed",
      journal: journalLog,
      artifacts,
      taskResults,
    });

    if (opts.dry) {
      printDrySummary(cards.length, artifacts, journalLog);
      return;
    }

    await platformFetch(config, "POST", "/api/night/runs", report);
    console.log(
      `\n밤 보고 완료 — 산출물 ${artifacts.length} · 생산 ${taskResults.filter((r) => r.status === "produced").length} · 건너뜀 ${taskResults.filter((r) => r.status === "skipped").length} · 실패 ${taskResults.filter((r) => r.status === "failed").length}`
    );
    console.log("아침에 웹에서 승인/반려하세요.");
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (opts.dry) throw err;
    // 전체 실패 — 지금까지의 일지/산출물을 실패 상태로 보고한다.
    const failReport: NightRunReport = {
      startedAt,
      finishedAt: nowIso(),
      status: "failed",
      error: msg,
      journal: journalLog,
      artifacts,
      taskResults,
    };
    await platformFetch(config, "POST", "/api/night/runs", failReport).catch(() => {});
    throw err;
  }
}

function printDrySummary(cardCount: number, artifacts: ProducedArtifact[], journalLog: JournalEntry[]): void {
  console.log(`\n─── dry 요약 (전송 없음) ───`);
  console.log(`카드 처리: ${cardCount} · 산출물: ${artifacts.length}`);
  if (artifacts.length) {
    console.log("산출물 제목:");
    for (const a of artifacts) console.log(`  - ${a.title} (${a.content.length}자)`);
  }
  console.log("일지 미리보기:");
  for (const e of journalLog.slice(0, 12)) {
    console.log(`  [${e.kind}]${e.policyId ? ` [P:${e.policyId}]` : ""} ${e.text}`);
  }
  if (journalLog.length > 12) console.log(`  … 외 ${journalLog.length - 12}개`);
}
