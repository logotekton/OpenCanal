#!/usr/bin/env node
// opencanal-runner — your agent's brain, on your machine, on your subscription.
// Commands: login | link opencrab | start | status | test "<question>"

import { createInterface } from "node:readline/promises";
import { hostname } from "node:os";
import { OpenCanalNode } from "@opencanal/node-sdk";
import { loadConfig, saveConfig, configPath } from "./config";
import { PlatformApi } from "./api";
import { OpencrabClient } from "./sources/opencrab";
import { ReceiptIngester } from "./ingest";
import { ClaudeAdapter } from "./brain/claude";
import { CodexAdapter } from "./brain/codex";
import type { BrainAdapter } from "./brain/adapter";

const VERSION = "0.1.0";

function makeBrain(provider: string): BrainAdapter {
  if (provider === "codex") {
    console.warn("[brain] codex adapter is EXPERIMENTAL");
    return new CodexAdapter();
  }
  return new ClaudeAdapter();
}

async function ask(question: string): Promise<string> {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer = await rl.question(question);
  rl.close();
  return answer.trim();
}

async function cmdLogin(): Promise<void> {
  const config = loadConfig();
  const platformUrl =
    (await ask(`플랫폼 URL [${config.platformUrl}]: `)) || config.platformUrl;
  const code = await ask("페어링 코드 (웹 → Runner 설정에서 발급): ");
  if (!code) {
    console.error("코드가 필요합니다.");
    process.exit(1);
  }

  const result = await PlatformApi.pair(platformUrl, code.toUpperCase(), hostname(), VERSION);
  saveConfig({
    ...config,
    platformUrl,
    gatewayUrl: config.gatewayUrl,
    deviceToken: result.deviceToken,
    agentId: result.agentId,
    handle: result.handle,
  });
  console.log(`✓ 페어링 완료 — @${result.handle} (${result.displayName})`);
  console.log(`  설정 저장: ${configPath}`);
  console.log(`  다음: opencanal-runner link opencrab  (OpenCrab 연결, 선택)`);
  console.log(`        opencanal-runner start          (러너 시작)`);
}

async function cmdLinkOpencrab(): Promise<void> {
  const config = loadConfig();
  if (!config.deviceToken) {
    console.error("먼저 `opencanal-runner login`으로 페어링하세요.");
    process.exit(1);
  }

  const token = await ask("OpenCrab ocm_ 토큰 (이 머신에만 저장됩니다): ");
  if (!token.startsWith("ocm_")) {
    console.error("ocm_ 으로 시작하는 토큰이어야 합니다.");
    process.exit(1);
  }
  const packId = await ask("팩/프로젝트 ID: ");

  console.log("opencrab.sh 연결 확인 중...");
  const client = new OpencrabClient(token);
  const attestation = await client.validateAndAttest(packId);
  console.log(`✓ 연결 확인 — manifest hash: ${attestation.manifestHash}`);

  // Find the agent's pending opencrab source on the platform and attest it
  const api = new PlatformApi(config);
  const inbox = await api.inbox();
  const source = inbox.sources.find((s) => s.kind === "opencrab_pack");
  if (source) {
    await api.attestSource(source.id, {
      packId: attestation.packId,
      manifestHash: attestation.manifestHash,
      spaces: attestation.spaces,
    });
    console.log(`✓ 플랫폼에 attest 완료 — 프로필에 "OpenCrab linked" 표시됩니다.`);
  } else {
    console.warn(
      "! 플랫폼에 opencrab_pack 소스가 없습니다. 웹에서 agent에 OpenCrab 소스를 추가하면 자동 attest됩니다."
    );
  }

  saveConfig({ ...config, opencrab: { token, packId } });
  console.log(`✓ 토큰 저장 (로컬 전용): ${configPath}`);
}

async function cmdStart(): Promise<void> {
  const config = loadConfig();
  if (!config.deviceToken || !config.agentId) {
    console.error("먼저 `opencanal-runner login`으로 페어링하세요.");
    process.exit(1);
  }

  const api = new PlatformApi(config);
  const brain = makeBrain(config.brain.provider);
  // OpenCrab: 페르소나 컨텍스트(persona 훅) + 거래 이력 ingest(onConnect)에 쓰인다.
  const opencrab = config.opencrab?.token
    ? new OpencrabClient(config.opencrab.token, config.opencrab.mcpUrl)
    : null;
  const ingester = new ReceiptIngester(api, opencrab);

  // 러너 = node-sdk(OpenCanal Node Protocol) 위의 얇은 래퍼.
  // 프로토콜(페어링/WS/드레인/멱등/constitution/큐/capability)은 SDK가, 두뇌·페르소나·ingest는 러너가.
  const node = new OpenCanalNode({
    platformUrl: config.platformUrl,
    gatewayWsUrl: config.gatewayUrl,
    deviceToken: config.deviceToken,
    handle: config.handle,
    displayName: config.handle,
    brain: ({ systemPrompt, userPrompt }) => brain.complete(systemPrompt, userPrompt),
    persona: opencrab ? (q) => opencrab.personaContext(q) : undefined,
    limits: { concurrency: config.limits.concurrency, repliesPerHour: config.limits.repliesPerHour },
    onConnect: () => {
      void ingester.run();
    },
    onApprovalRequired: ({ roomId }) =>
      console.log(`[runner] 승인 대기 — 웹에서 확인하세요 (room ${roomId})`),
    logger: (m) => console.log(m),
  });

  console.log(`OpenCanal Runner v${VERSION}`);
  console.log(`  agent: @${config.handle}`);
  console.log(`  brain: ${brain.name}${config.opencrab ? ` · OpenCrab pack: ${config.opencrab.packId}` : ""}`);
  console.log(`  limits: ${config.limits.concurrency} concurrent, ${config.limits.repliesPerHour}/hour`);

  await node.start(); // WS가 프로세스를 살려둔다 (별도 listen 포트 없음)
}

async function cmdStatus(): Promise<void> {
  const config = loadConfig();
  console.log(`OpenCanal Runner v${VERSION} — doctor`);
  console.log(`  config: ${configPath}`);
  console.log(`  paired: ${config.deviceToken ? `yes (@${config.handle})` : "no — run login"}`);
  console.log(`  brain: ${config.brain.provider}`);
  console.log(`  opencrab: ${config.opencrab ? `linked (pack: ${config.opencrab.packId})` : "not linked"}`);

  // Platform reachability
  try {
    const res = await fetch(`${config.platformUrl}/api/auth/session`, {
      signal: AbortSignal.timeout(5000),
    });
    console.log(`  platform: ${res.ok ? "reachable" : `HTTP ${res.status}`} (${config.platformUrl})`);
  } catch {
    console.log(`  platform: UNREACHABLE (${config.platformUrl})`);
  }

  // OpenCrab reachability
  if (config.opencrab) {
    try {
      const client = new OpencrabClient(config.opencrab.token, config.opencrab.mcpUrl);
      await client.validateAndAttest(config.opencrab.packId);
      console.log("  opencrab.sh: token valid");
    } catch (err) {
      console.log(`  opencrab.sh: FAILED — ${err instanceof Error ? err.message : err}`);
    }
  }
}

async function cmdTest(question: string): Promise<void> {
  const config = loadConfig();
  const brain = makeBrain(config.brain.provider);

  let persona = "";
  if (config.opencrab) {
    console.log("[test] OpenCrab에서 페르소나 컨텍스트 조회 중...");
    const client = new OpencrabClient(config.opencrab.token, config.opencrab.mcpUrl);
    persona = await client.personaContext(question);
  }

  const { buildConstitution } = await import("@opencanal/shared");
  const systemPrompt = buildConstitution({
    agentHandle: config.handle ?? "test-agent",
    agentDisplayName: config.handle ?? "test-agent",
    roomType: "question",
    counterpart: { handle: "tester", type: "personal", verificationLevel: "L0" },
    personaBlock: persona,
  });

  console.log(`[test] ${brain.name} 두뇌 호출 중...`);
  const raw = await brain.complete(systemPrompt, `# New message from @tester\n${question}\n\nReply now, following the output format exactly.`);
  const { parseBrainOutput } = await import("./brain/adapter");
  const output = parseBrainOutput(raw);

  console.log("\n─── 응답 ───");
  console.log(output.content);
  if (output.claims?.length) {
    console.log("\n─── claims ───");
    for (const c of output.claims) console.log(`[${c.type}] ${c.text}`);
  }
  console.log(`\nneeds_approval: ${output.needs_approval}`);
}

// ── dispatch ──

const [, , command, ...args] = process.argv;

try {
  switch (command) {
    case "login":
      await cmdLogin();
      break;
    case "link":
      if (args[0] === "opencrab") await cmdLinkOpencrab();
      else console.error("usage: opencanal-runner link opencrab");
      break;
    case "start":
      await cmdStart();
      break;
    case "status":
      await cmdStatus();
      break;
    case "test":
      if (!args.length) console.error('usage: opencanal-runner test "질문"');
      else await cmdTest(args.join(" "));
      break;
    default:
      console.log(`OpenCanal Runner v${VERSION}

usage:
  opencanal-runner login            웹에서 발급한 페어링 코드로 연결
  opencanal-runner link opencrab    OpenCrab 온톨로지 팩 연결 (ocm_ 토큰은 로컬 전용)
  opencanal-runner start            러너 시작 (agent가 온라인이 됩니다)
  opencanal-runner status           연결 상태 진단
  opencanal-runner test "질문"      플랫폼 없이 두뇌+페르소나 로컬 테스트`);
  }
} catch (err) {
  console.error(`오류: ${err instanceof Error ? err.message : err}`);
  process.exit(1);
}
