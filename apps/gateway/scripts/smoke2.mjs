// Smoke 2: (a) admin 승인 → 주황 딱지, (b) gateway WS 실시간 push
import WebSocket from "ws";

process.env.DATABASE_URL ??= "postgresql://opencanal:opencanal_dev@localhost:5433/opencanal";
const { prisma } = await import("@opencanal/db");
const BASE = "http://localhost:3000";
const GW = "ws://localhost:8787";

class Session {
  constructor() { this.cookies = new Map(); }
  cookieHeader() { return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; "); }
  absorb(res) {
    for (const c of res.headers.getSetCookie?.() ?? []) {
      const [pair] = c.split(";");
      const i = pair.indexOf("=");
      this.cookies.set(pair.slice(0, i).trim(), pair.slice(i + 1).trim());
    }
  }
  async fetch(path, options = {}) {
    const res = await fetch(`${BASE}${path}`, { ...options, headers: { ...(options.headers ?? {}), cookie: this.cookieHeader() }, redirect: "manual" });
    this.absorb(res);
    return res;
  }
  async login(email, name) {
    const { csrfToken } = await (await this.fetch("/api/auth/csrf")).json();
    await this.fetch("/api/auth/callback/dev-email", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ csrfToken, email, name }),
    });
  }
  async json(path, options) {
    const res = await this.fetch(path, options);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(`${path} → ${res.status}: ${JSON.stringify(body)}`);
    return body;
  }
}
const post = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
let pass = 0;
const ok = (label, cond) => { if (!cond) throw new Error(`FAIL: ${label}`); console.log(`  ✓ ${label}`); pass++; };

// ── A. Admin approval → badge ──
console.log("A. 관리자 승인 → 주황 딱지");
const admin = new Session();
await admin.login("ghddudxor12@gmail.com", "Founder");

const pendingReq = await prisma.verificationRequest.findFirst({ where: { state: "pending" }, include: { agent: true } });
ok("pending 검증신청 존재 (smoke1에서 생성)", !!pendingReq);
await admin.json(`/api/admin/verification/${pendingReq.id}`, post({ decision: "approved" }));
const agentAfter = await prisma.agent.findUnique({ where: { id: pendingReq.agentId }, include: { badge: true } });
ok("agent L2로 승급", agentAfter.verificationLevel === "L2");
ok("VerificationBadge 생성 (주황 딱지)", !!agentAfter.badge);

// non-admin은 거부되는지
const alice = new Session();
await alice.login("alice@test.com", "Alice");
const denied = await alice.fetch(`/api/admin/verification/${pendingReq.id}`, post({ decision: "approved" }));
ok("일반 사용자 admin API 403", denied.status === 403);

// ── B. Gateway WS: pairing → connect → presence → realtime push ──
console.log("B. 게이트웨이 WS 실시간");
const suffix = Date.now().toString(36);
const bobAgent = await alice.json("/api/agents", post({ handle: `bob-${suffix}`, displayName: "Bob Agent", type: "personal", sourceKind: "none" }));
const pairing = await alice.json(`/api/agents/${bobAgent.id}/pairing`, { method: "POST" });
const paired = await (await fetch(`${BASE}/api/runner/pair`, post({ code: pairing.code, deviceName: "ws-test" }))).json();

const events = [];
const ws = new WebSocket(`${GW}/runner`, { headers: { Authorization: `Bearer ${paired.deviceToken}` } });
await new Promise((resolve, reject) => {
  ws.on("open", resolve);
  ws.on("error", reject);
  setTimeout(() => reject(new Error("ws connect timeout")), 5000);
});
ws.on("message", (raw) => events.push(JSON.parse(raw.toString())));
await new Promise((r) => setTimeout(r, 800));
ok("hello 수신", events.some((e) => e.type === "hello"));

const agentNow = await prisma.agent.findUnique({ where: { id: bobAgent.id } });
ok("presence online", agentNow.status === "online");

// (1) bob 소유자(alice)가 bob에게 지시 → bob 러너 WS로 room.instruction push되는지
const founderAgentRow = await prisma.agent.findFirst({ where: { handle: { startsWith: "founder-" } }, orderBy: { createdAt: "desc" } });
const room = await alice.json("/api/rooms", post({ targetAgentId: founderAgentRow.id, initiatorAgentId: bobAgent.id, type: "question" }));
await alice.json(`/api/rooms/${room.roomId}/instructions`, post({ content: "상대에게 인사해" }));
await new Promise((r) => setTimeout(r, 1500));
const pushedIns = events.find((e) => e.type === "room.instruction");
ok("room.instruction 실시간 push 수신", pushedIns?.content.includes("인사"));
ok("instruction에 상대 카드 포함", pushedIns?.counterpart?.agentId === founderAgentRow.id);

// (2) founder agent의 (가짜) 러너가 bob에게 메시지 → bob 러너 WS로 room.message push되는지
const founderPairing = await admin.json(`/api/agents/${founderAgentRow.id}/pairing`, { method: "POST" });
const founderPaired = await (await fetch(`${BASE}/api/runner/pair`, post({ code: founderPairing.code, deviceName: "ws-test-founder" }))).json();
// bob의 지시를 bob 러너 대신 직접 수행 (WS로 받은 instructionId 사용)
await fetch(`${BASE}/api/runner/messages`, {
  method: "POST",
  headers: { Authorization: `Bearer ${paired.deviceToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({ roomId: room.roomId, instructionId: pushedIns.instructionId, content: "안녕하세요, Bob의 agent입니다.", needsApproval: false }),
});
// founder 러너가 자동응답 → bob WS에 room.message 도착해야 함
const founderInbox = await (await fetch(`${BASE}/api/runner/inbox`, { headers: { Authorization: `Bearer ${founderPaired.deviceToken}` } })).json();
const incoming = founderInbox.messages.find((m) => m.roomId === room.roomId);
await fetch(`${BASE}/api/runner/messages`, {
  method: "POST",
  headers: { Authorization: `Bearer ${founderPaired.deviceToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({ roomId: room.roomId, inReplyToId: incoming.messageId, content: "반갑습니다, 실시간 push 테스트 응답입니다", needsApproval: false }),
});
await new Promise((r) => setTimeout(r, 1500));
const pushed = events.find((e) => e.type === "room.message");
ok("room.message 실시간 push 수신", pushed?.content.includes("실시간"));

ws.close();
await new Promise((r) => setTimeout(r, 800));
const agentOffline = await prisma.agent.findUnique({ where: { id: bobAgent.id } });
ok("연결 종료 → presence offline", agentOffline.status === "offline");

console.log(`\n✅ 스모크2 통과 — ${pass}개 검증`);
await prisma.$disconnect();
