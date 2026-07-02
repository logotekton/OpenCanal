// Night loop 프로토콜 (피벗 v2 — docs/DIRECTION.md)
// 러너 ↔ 플랫폼의 계약: 큐(정책·지시·카드·교정) pull → 밤 생산 → 결과 보고 → 아침 리뷰.
// 원칙: 모든 판단에 정책 출처(policyId)가 남는다 — 반려 교정이 정확한 정책을 겨냥하게 (provenance).

import { z } from "zod";

// ───────────────────────── 정책 / 지시 ─────────────────────────

export const NIGHT_POLICY_KINDS = ["decision", "red_flag", "style", "playbook"] as const;
export type NightPolicyKind = (typeof NIGHT_POLICY_KINDS)[number];

export const nightPolicySchema = z.object({
  id: z.string(),
  kind: z.enum(NIGHT_POLICY_KINDS),
  text: z.string().min(1),
  active: z.boolean(),
});
export type NightPolicy = z.infer<typeof nightPolicySchema>;

export const nightDirectiveSchema = z.object({
  id: z.string(),
  content: z.string().min(1),
});
export type NightDirective = z.infer<typeof nightDirectiveSchema>;

// ───────────────────────── 작업 카드 ─────────────────────────

export const taskCardSchema = z.object({
  id: z.string(),
  title: z.string().min(1),
  brief: z.string().min(1), // 무엇을 만들지
  originPolicyId: z.string().nullish(),
  originNote: z.string().nullish(), // 왜 이 작업인가 (판단 근거)
});
export type TaskCard = z.infer<typeof taskCardSchema>;

// ───────────────────────── 일지 (스펙터클의 원천) ─────────────────────────

export const JOURNAL_ENTRY_KINDS = ["plan", "produce", "decision", "correction", "note"] as const;

export const journalEntrySchema = z.object({
  at: z.string(), // ISO timestamp
  kind: z.enum(JOURNAL_ENTRY_KINDS),
  text: z.string(),
  taskId: z.string().nullish(),
  policyId: z.string().nullish(), // 이 판단의 정책 출처
});
export type JournalEntry = z.infer<typeof journalEntrySchema>;

// ───────────────────────── 교정 (Correct 루프) ─────────────────────────

// 아침 리뷰에서 반려된 산출물 — 러너가 다음 밤 시작 시 팩으로 재ingest하고 ack한다.
export const nightCorrectionSchema = z.object({
  artifactId: z.string(),
  artifactTitle: z.string(),
  taskTitle: z.string().nullish(),
  reason: z.string(), // 반려 사유 — 팩 갱신의 원료
  reviewedAt: z.string(),
});
export type NightCorrection = z.infer<typeof nightCorrectionSchema>;

// ───────────────────────── 큐 (GET /api/night/queue) ─────────────────────────

export const nightQueueSchema = z.object({
  agent: z.object({
    id: z.string(),
    handle: z.string(),
    displayName: z.string(),
  }),
  ownerName: z.string().nullish(),
  policies: z.array(nightPolicySchema),
  directives: z.array(nightDirectiveSchema),
  tasks: z.array(taskCardSchema),
  corrections: z.array(nightCorrectionSchema), // 미ingest 반려들
});
export type NightQueue = z.infer<typeof nightQueueSchema>;

// ───────────────────────── 실행 보고 (POST /api/night/runs) ─────────────────────────

export const producedArtifactSchema = z.object({
  taskId: z.string(),
  kind: z.enum(["markdown", "text"]).default("markdown"),
  title: z.string().min(1),
  content: z.string().min(1),
});
export type ProducedArtifact = z.infer<typeof producedArtifactSchema>;

export const taskResultSchema = z.object({
  taskId: z.string(),
  status: z.enum(["produced", "skipped", "failed"]),
  note: z.string().nullish(), // skipped/failed의 근거 (일지에도 남는다)
});
export type TaskResult = z.infer<typeof taskResultSchema>;

export const nightRunReportSchema = z.object({
  startedAt: z.string(),
  finishedAt: z.string(),
  status: z.enum(["completed", "failed"]),
  error: z.string().nullish(),
  journal: z.array(journalEntrySchema),
  artifacts: z.array(producedArtifactSchema),
  taskResults: z.array(taskResultSchema),
});
export type NightRunReport = z.infer<typeof nightRunReportSchema>;

// ───────────────────────── 교정 ack (POST /api/night/corrections/ack) ─────────────────────────

export const correctionAckSchema = z.object({
  artifactIds: z.array(z.string()).min(1),
});
export type CorrectionAck = z.infer<typeof correctionAckSchema>;

// ───────────────────────── 아침 리뷰 (POST /api/night/artifacts/[id]/review) ─────────────────────────

export const reviewInputSchema = z
  .object({
    decision: z.enum(["approved", "rejected"]),
    reason: z.string().max(2000).nullish(),
  })
  .refine((r) => r.decision === "approved" || (r.reason && r.reason.trim().length > 0), {
    message: "반려에는 사유가 필요하다 — 사유가 곧 팩 교정의 원료다",
  });
export type ReviewInput = z.infer<typeof reviewInputSchema>;

// ───────────────────────── Night constitution ─────────────────────────

export interface NightConstitutionContext {
  agentHandle: string;
  agentDisplayName: string;
  ownerName?: string | null;
  policies: NightPolicy[];
  directives: NightDirective[];
  personaBlock?: string; // OpenCrab 팩 컨텍스트 (opencrab_query 결과)
}

// 밤 생산용 헌법 — v1 constitution의 자율 생산 변형.
// 정책이 [P:id]로 인용 가능하게 주입된다: 두뇌가 판단 기록에 정책 id를 남길 수 있도록.
export function buildNightConstitution(ctx: NightConstitutionContext): string {
  const byKind = (kind: NightPolicyKind) => ctx.policies.filter((p) => p.kind === kind && p.active);
  const policyLines = (kind: NightPolicyKind, label: string) => {
    const items = byKind(kind);
    if (items.length === 0) return null;
    return `## ${label}\n${items.map((p) => `- [P:${p.id}] ${p.text}`).join("\n")}`;
  };

  const policyBlock = [
    policyLines("decision", "Decision policies (판단 기준 — 무엇이 할 가치가 있는가)"),
    policyLines("red_flag", "Red flags (금지선 — 위반하느니 작업을 건너뛴다)"),
    policyLines("style", "Style (소유자다움 — 모든 산출물의 목소리)"),
    policyLines("playbook", "Playbooks (요령 — 실행 방법)"),
  ]
    .filter(Boolean)
    .join("\n\n");

  const directiveBlock =
    ctx.directives.length > 0
      ? `\n\n# Standing directives (소유자의 상시 지시)\n${ctx.directives.map((d) => `- ${d.content}`).join("\n")}`
      : "";

  return `You are "${ctx.agentDisplayName}" (@${ctx.agentHandle}), the autonomous night worker of your owner${ctx.ownerName ? ` (${ctx.ownerName})` : ""} on OpenCanal. While your owner sleeps, you produce real artifacts in their voice and by their judgment. Every artifact you produce will be reviewed by your owner in the morning — approval means it goes out into the world under their name; rejection (with a reason) becomes a correction that updates your judgment pack.

# Persona context (from your owner's knowledge pack)
${ctx.personaBlock || "(no pack context available this run — be conservative, do not invent facts about your owner)"}

# Judgment policies — these ARE your owner's judgment. Cite them.
${policyBlock || "(no policies defined yet — act very conservatively and note the absence in your journal)"}${directiveBlock}

# Rules (Night constitution)
1. Your output is a REAL artifact that may be published under your owner's name. Quality over quantity — a skipped task with a good reason beats a mediocre artifact.
2. Every consequential choice must trace to a policy. When you follow or are constrained by a policy, cite its id like [P:xxx].
3. If a task conflicts with a red flag, SKIP it and say which red flag and why.
4. Never invent facts about your owner, their work, or their domain. If the pack doesn't support a claim, either omit it or mark it clearly as a suggestion.
5. Do not commit, promise, pay, or submit anything — you produce drafts and packages; your owner's morning approval is the only gate to the outside world.
6. Write in your owner's language and voice (persona/style policies). Default to Korean if unclear.`;
}

// ───────────────────────── 두뇌 출력 파싱 (밤 생산) ─────────────────────────

export interface NightBrainOutput {
  title: string;
  content: string;
  decisions: { text: string; policyId?: string | null }[]; // 일지에 남길 판단 기록
  skipped?: { reason: string; policyId?: string | null } | null;
}

// 밤 두뇌 출력 계약: JSON {title, content, decisions:[{text, policyId?}], skipped?}.
// 모델이 JSON을 어겨도 산출물을 잃지 않도록 관대하게 폴백한다 (전체 텍스트 = content).
export function parseNightBrainOutput(raw: string, fallbackTitle: string): NightBrainOutput {
  const text = raw.trim();
  const jsonCandidate = text.startsWith("```")
    ? text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "")
    : text;
  try {
    const parsed = JSON.parse(jsonCandidate) as Partial<NightBrainOutput> & { content?: string };
    const skipped =
      parsed.skipped && typeof parsed.skipped === "object" && typeof parsed.skipped.reason === "string"
        ? { reason: parsed.skipped.reason, policyId: parsed.skipped.policyId ?? null }
        : null;
    // skipped 응답은 content가 비어 있을 수 있다 — content 유무만으로 폴백하면 skipped가 유실된다.
    if ((typeof parsed.content === "string" && parsed.content.length > 0) || skipped) {
      return {
        title: typeof parsed.title === "string" && parsed.title ? parsed.title : fallbackTitle,
        content: typeof parsed.content === "string" ? parsed.content : "",
        decisions: Array.isArray(parsed.decisions)
          ? parsed.decisions
              .filter((d): d is { text: string; policyId?: string | null } => typeof d?.text === "string")
              .map((d) => ({ text: d.text, policyId: d.policyId ?? null }))
          : [],
        skipped,
      };
    }
  } catch {
    // not JSON — fall through
  }
  return { title: fallbackTitle, content: text, decisions: [], skipped: null };
}
