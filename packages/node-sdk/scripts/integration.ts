// R2 통합 테스트 — @opencanal/node-sdk가 실제 검증 노드로 동작하는지.
// 가짜 두뇌(LLM 호출 없음)로 두 SDK 노드를 WS 연결 → 지시→메시지→자동응답 흐름 검증.
// 실행: pnpm --filter @opencanal/node-sdk exec tsx scripts/integration.ts
import { OpenCanalNode, pair } from "../src/index";

const BASE = "http://localhost:3000";
const GW = "ws://localhost:8787";

class Session {
  cookies = new Map<string, string>();
  ch() { return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; "); }
  absorb(r: Response) { for (const c of (r.headers as any).getSetCookie?.() ?? []) { const [p] = c.split(";"); const i = p.indexOf("="); this.cookies.set(p.slice(0, i).trim(), p.slice(i + 1).trim()); } }
  async fetch(path: string, o: any = {}) { const r = await fetch(`${BASE}${path}`, { ...o, headers: { ...(o.headers ?? {}), cookie: this.ch() }, redirect: "manual" }); this.absorb(r); return r; }
  async login(email: string, name: string) { const { csrfToken } = await (await this.fetch("/api/auth/csrf")).json(); await this.fetch("/api/auth/callback/dev-email", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ csrfToken, email, name }) }); const s = await (await this.fetch("/api/auth/session")).json(); if (!s?.user?.email) throw new Error("login failed"); return s.user; }
  async json(path: string, o?: any) { const r = await this.fetch(path, o); const b = await r.json().catch(() => ({})); if (!r.ok) throw new Error(`${path} ${r.status}: ${JSON.stringify(b)}`); return b; }
}
const post = (b: any) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
let pass = 0;
const ok = (l: string, c: boolean) => { if (!c) throw new Error(`FAIL: ${l}`); console.log(`  ✓ ${l}`); pass++; };

// 가짜 두뇌 — constitution(systemPrompt)을 받았는지 확인하고 고정 JSON 계약 반환.
// mustInclude가 주어지면 capability 주입(R5)까지 검증한다.
function fakeBrain(label: string, mustInclude?: string) {
  return async ({ systemPrompt }: { systemPrompt: string }) => {
    if (!systemPrompt.includes("OpenCanal")) throw new Error("constitution not injected");
    if (mustInclude && !systemPrompt.includes(mustInclude))
      throw new Error(`capability not injected: ${mustInclude}`);
    return JSON.stringify({ content: `[${label}] 안녕하세요, SDK 노드 응답입니다.`, needs_approval: false });
  };
}

async function pairTok(owner: Session, agentId: string) {
  const p = await owner.json(`/api/agents/${agentId}/pairing`, { method: "POST" });
  const paired = await pair(BASE, p.code, "integration");
  return paired.deviceToken;
}

async function main() {
  const sfx = Date.now().toString(36);
  console.log("=== R2: node-sdk 통합 테스트 ===");
  const a = new Session(); await a.login(`sdk-a-${sfx}@test.com`, "A");
  const b = new Session(); await b.login(`sdk-b-${sfx}@test.com`, "B");
  const aAgent = await a.json("/api/agents", post({ handle: `sdk-a-${sfx}`, displayName: "A agent", type: "personal", sourceKind: "manual_profile", tastes: "x" }));
  const bAgent = await b.json("/api/agents", post({ handle: `sdk-b-${sfx}`, displayName: "B agent", type: "personal", sourceKind: "manual_profile", hobbies: "y" }));
  const aTok = await pairTok(a, aAgent.id);
  const bTok = await pairTok(b, bAgent.id);
  ok("페어링으로 deviceToken 획득", aTok.startsWith("ocd_") && bTok.startsWith("ocd_"));

  const nodeA = new OpenCanalNode({ platformUrl: BASE, gatewayWsUrl: GW, deviceToken: aTok, brain: fakeBrain("A"), logger: () => {} });
  // R5: B 노드는 어댑터 capability를 동기화한다. fakeBrain이 constitution에 capability 주입을 검증.
  const nodeB = new OpenCanalNode({
    platformUrl: BASE,
    gatewayWsUrl: GW,
    deviceToken: bTok,
    brain: fakeBrain("B", "숙박 예약 대행"),
    capabilities: [{ key: "lodging.book", label: "숙박 예약 대행", requiresApproval: true }],
    logger: () => {},
  });
  await nodeA.start(); await nodeB.start();
  await sleep(1200); // WS 연결 + hello

  const room = await a.json("/api/rooms", post({ targetAgentId: bAgent.id, initiatorAgentId: aAgent.id, type: "question" }));
  await a.json(`/api/rooms/${room.roomId}/instructions`, post({ content: "상대에게 인사해" }));
  console.log("  · 지시 전송 — SDK 노드가 처리할 때까지 대기");
  await sleep(4000); // A 노드: 지시→메시지, B 노드: 자동응답

  const thread = await a.json(`/api/rooms/${room.roomId}/messages`);
  const aMsg = thread.messages.find((m: any) => m.senderAgentId === aAgent.id);
  const bMsg = thread.messages.find((m: any) => m.senderAgentId === bAgent.id);
  ok("A 노드가 지시를 메시지로 작성", !!aMsg && aMsg.content.includes("[A]"));
  ok("B 노드가 자동응답", !!bMsg && bMsg.content.includes("[B]"));
  const insState = thread.instructions?.[0]?.status;
  ok("지시 processed 처리", insState === "processed");

  // R5: B의 능력이 어댑터로 동기화되어 공개 조회된다 (bMsg 성공 = constitution 주입까지 검증됨)
  const bCaps = await b.json(`/api/agents/${bAgent.id}/capabilities`);
  ok("B 노드 능력 동기화(어댑터 매핑)", bCaps.capabilities.some((c: any) => c.key === "lodging.book"));

  nodeA.stop(); nodeB.stop();
  await sleep(500);
  console.log(`\n✅ R2 통합 테스트 통과 — ${pass}개 검증 (SDK가 검증 노드로 동작)`);
}
main().then(() => process.exit(0)).catch((e) => { console.error("R2 통합 실패:", e); process.exit(1); });
