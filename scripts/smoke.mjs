// E2E smoke test (instruction-based flow):
// auth → agent → pairing → source attest → room → 지시 → agent 메시지 → 자동응답 → 거래 승인 게이트
const BASE = "http://localhost:3000";

class Session {
  constructor() {
    this.cookies = new Map();
  }
  cookieHeader() {
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
  }
  absorb(res) {
    const setCookies = res.headers.getSetCookie?.() ?? [];
    for (const c of setCookies) {
      const [pair] = c.split(";");
      const idx = pair.indexOf("=");
      this.cookies.set(pair.slice(0, idx).trim(), pair.slice(idx + 1).trim());
    }
  }
  async fetch(path, options = {}) {
    const res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: { ...(options.headers ?? {}), cookie: this.cookieHeader() },
      redirect: "manual",
    });
    this.absorb(res);
    return res;
  }
  async login(email, name) {
    const csrfRes = await this.fetch("/api/auth/csrf");
    const { csrfToken } = await csrfRes.json();
    await this.fetch("/api/auth/callback/dev-email", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ csrfToken, email, name }),
    });
    const session = await (await this.fetch("/api/auth/session")).json();
    if (!session?.user?.email) throw new Error("no session after login");
    return session.user;
  }
  async json(path, options) {
    const res = await this.fetch(path, options);
    const body = await res.json().catch(() => ({}));
    if (!res.ok)
      throw new Error(`${options?.method ?? "GET"} ${path} → ${res.status}: ${JSON.stringify(body)}`);
    return body;
  }
}

const post = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

let pass = 0;
function ok(label, cond) {
  if (!cond) throw new Error(`FAIL: ${label}`);
  console.log(`  ✓ ${label}`);
  pass++;
}

/** 러너 시뮬레이터 — 실제 LLM 없이 inbox 드레인 + 지시/응답 수행 */
class FakeRunner {
  constructor(deviceToken) {
    this.headers = { Authorization: `Bearer ${deviceToken}`, "Content-Type": "application/json" };
  }
  async inbox() {
    return (await fetch(`${BASE}/api/runner/inbox`, { headers: this.headers })).json();
  }
  async reply(payload) {
    const res = await fetch(`${BASE}/api/runner/messages`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(`runner reply → ${res.status}: ${JSON.stringify(body)}`);
    return body;
  }
}

async function pairRunner(ownerSession, agentId) {
  const pairing = await ownerSession.json(`/api/agents/${agentId}/pairing`, { method: "POST" });
  const paired = await (
    await fetch(`${BASE}/api/runner/pair`, post({ code: pairing.code, deviceName: "smoke" }))
  ).json();
  if (!paired.deviceToken) throw new Error("pairing failed");
  return new FakeRunner(paired.deviceToken);
}

// ── 1. Users ──
console.log("1. 사용자 2명 로그인 (admin + 일반)");
const suffix = Date.now().toString(36);
const admin = new Session();
const adminUser = await admin.login("ghddudxor12@gmail.com", "Founder");
const alice = new Session();
// 실행마다 고유 이메일 — 시간당 지시 rate limit이 반복 실행에 누적되지 않도록
await alice.login(`alice-${suffix}@test.com`, "Alice");
ok("admin/alice 로그인", !!adminUser);

// ── 2. Agents ──
console.log("2. agent 생성");
const founderAgent = await admin.json(
  "/api/agents",
  post({
    handle: `founder-${suffix}`,
    displayName: "Founder Agent",
    type: "personal",
    sourceKind: "opencrab_pack",
    packId: "founder_persona",
  })
);
const aliceAgent = await alice.json(
  "/api/agents",
  post({
    handle: `alice-${suffix}`,
    displayName: "Alice Agent",
    type: "personal",
    sourceKind: "manual_profile",
    tastes: "매운 음식",
    hobbies: "등산",
    skills: "디자인",
  })
);
ok("agent 2개 생성", !!founderAgent.id && !!aliceAgent.id);
const dup = await admin.fetch("/api/agents", post({ handle: `founder-${suffix}`, displayName: "x" }));
ok("핸들 중복 409", dup.status === 409);

// ── 3. Verification ──
console.log("3. 검증 신청");
await alice.json(
  `/api/agents/${aliceAgent.id}/verification`,
  post({ note: "본인입니다", officialUrl: "https://alice.kr" })
);
const dupReq = await alice.fetch(`/api/agents/${aliceAgent.id}/verification`, post({ note: "again" }));
ok("중복 검증신청 409", dupReq.status === 409);

// ── 4. Runners ──
console.log("4. 러너 페어링 (양쪽)");
const founderRunner = await pairRunner(admin, founderAgent.id);
const aliceRunner = await pairRunner(alice, aliceAgent.id);
ok("양쪽 러너 페어링", true);

// ── 5. Source attest ──
console.log("5. OpenCrab 소스 attest");
const inbox0 = await founderRunner.inbox();
const ocSource = inbox0.sources.find((s) => s.kind === "opencrab_pack");
ok("opencrab 소스 pending 존재", ocSource?.status === "pending");
await fetch(`${BASE}/api/runner/sources/${ocSource.id}/attest`, {
  method: "POST",
  headers: founderRunner.headers,
  body: JSON.stringify({ packId: "founder_persona", manifestHash: "abc123", nodeCount: 42 }),
});
const inbox1 = await founderRunner.inbox();
ok("attest 후 linked", inbox1.sources.find((s) => s.kind === "opencrab_pack")?.status === "linked");

// ── 6. Room + Instruction (지시 기반 — 직접 메시지는 불가능) ──
console.log("6. 룸 + 지시 (alice → 자기 agent에게 지시)");
const room = await alice.json(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "question" })
);
ok("룸 생성", !!room.roomId);

const directMsg = await alice.fetch(`/api/rooms/${room.roomId}/messages`, post({ content: "직접 메시지" }));
ok("직접 메시지 전송 차단 (405)", directMsg.status === 405);

const ins = await alice.json(
  `/api/rooms/${room.roomId}/instructions`,
  post({ content: "상대에게 인사하고 취미를 물어봐" })
);
ok("지시 생성", !!ins.instructionId);

// ── 7. Alice 러너가 지시 수행 → agent 메시지 ──
console.log("7. 러너가 지시 수행");
const aliceInbox = await aliceRunner.inbox();
const pendingIns = aliceInbox.instructions.find((i) => i.instructionId === ins.instructionId);
ok("러너 inbox에 지시 도착", pendingIns?.content.includes("취미"));
ok("지시에 상대 정보 포함", pendingIns.counterpart?.agentId === founderAgent.id);

const sent = await aliceRunner.reply({
  roomId: room.roomId,
  instructionId: ins.instructionId,
  content: "안녕하세요! 저는 Alice의 agent입니다. 소유자분의 취미가 궁금합니다.",
  needsApproval: false,
});
ok("지시 수행 → 메시지 전달", sent.requiresApproval === false);

const aliceView = await alice.json(`/api/rooms/${room.roomId}/messages`);
ok(
  "지시가 processed로 표시",
  aliceView.instructions.find((i) => i.id === ins.instructionId)?.status === "processed"
);
const reuse = await aliceRunner
  .reply({ roomId: room.roomId, instructionId: ins.instructionId, content: "again", needsApproval: false })
  .catch((e) => e.message);
ok("지시 중복 수행 409", String(reuse).includes("409"));

// ── 8. Founder 러너 자동응답 ──
console.log("8. 상대 러너 자동응답");
const founderInbox = await founderRunner.inbox();
const incoming = founderInbox.messages.find((m) => m.roomId === room.roomId);
ok("상대 inbox에 메시지 도착", incoming?.content.includes("취미"));
await founderRunner.reply({
  roomId: room.roomId,
  inReplyToId: incoming.messageId,
  content: "등산과 온톨로지 설계를 좋아합니다.",
  claims: [{ type: "claim", text: "취미는 등산" }],
  needsApproval: false,
});
const aliceView2 = await alice.json(`/api/rooms/${room.roomId}/messages`);
ok("alice가 응답 조회 가능", aliceView2.messages.some((m) => m.content.includes("등산")));

// ── 9. Trade room: 권한 게이트 → 승인 게이트 → Receipt ──
console.log("9. 거래 룸: 권한/승인 게이트 + 합의 확정");
// can_negotiate가 꺼진 상태(기본값)에서는 거래 룸 생성이 차단되어야 한다
const gateBlocked = await alice.fetch(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "trade" })
);
ok("can_negotiate 없이 거래 룸 403", gateBlocked.status === 403);
await alice.json(`/api/agents/${aliceAgent.id}/permissions`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ can_negotiate: true }),
});
// 상대(founder)가 협상 권한을 안 켰으면 여전히 차단되어야 한다 (양측 옵트인)
const targetGate = await alice.fetch(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "trade" })
);
ok("상대 can_negotiate 없이 거래 룸 403", targetGate.status === 403);
await admin.json(`/api/agents/${founderAgent.id}/permissions`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ can_negotiate: true }),
});
const tradeRoom = await alice.json(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "trade" })
);
ok("협상 권한 켠 후 거래 룸 생성", !!tradeRoom.roomId);
const tradeIns = await alice.json(
  `/api/rooms/${tradeRoom.roomId}/instructions`,
  post({ content: "모니터를 5만원에 사고 싶다고 제안해" })
);
const aliceInbox2 = await aliceRunner.inbox();
const tradePending = aliceInbox2.instructions.find((i) => i.instructionId === tradeIns.instructionId);
const held = await aliceRunner.reply({
  roomId: tradeRoom.roomId,
  instructionId: tradePending.instructionId,
  content: "모니터를 5만원에 구매하고 싶습니다.",
  needsApproval: false,
});
ok("거래 룸은 항상 승인 필요", held.requiresApproval === true);

const founderView = await admin.json(`/api/rooms/${tradeRoom.roomId}/messages`);
ok("승인 전 상대에게 안 보임", !founderView.messages.some((m) => m.content.includes("5만원")));

const aliceTradeView = await alice.json(`/api/rooms/${tradeRoom.roomId}/messages`);
const heldMsg = aliceTradeView.messages.find((m) => m.content.includes("5만원"));
ok("소유자에게는 보류 메시지 + 승인요청", !!heldMsg?.approvalRequest?.id);
await alice.json(`/api/approvals/${heldMsg.approvalRequest.id}`, post({ decision: "approved" }));
const founderView2 = await admin.json(`/api/rooms/${tradeRoom.roomId}/messages`);
ok("승인 후 상대에게 보임", founderView2.messages.some((m) => m.content.includes("5만원")));

// 합의 확정 (Receipt) — 제안 받은 쪽(founder)만 확정 가능
const proposal = founderView2.messages.find((m) => m.content.includes("5만원"));
const selfConfirm = await alice.fetch(`/api/rooms/${tradeRoom.roomId}/receipts`, post({ proposalMessageId: proposal.id }));
ok("자기 제안 확정 차단 403", selfConfirm.status === 403);
const receipt = await admin.json(`/api/rooms/${tradeRoom.roomId}/receipts`, post({ proposalMessageId: proposal.id }));
ok("합의 확정 → Receipt 생성", !!receipt.receiptId);
const doubleConfirm = await admin.fetch(`/api/rooms/${tradeRoom.roomId}/receipts`, post({ proposalMessageId: proposal.id }));
ok("중복 확정 409", doubleConfirm.status === 409);
const receiptPage = await admin.fetch(`/receipts/${receipt.receiptId}`);
ok("Receipt 페이지 접근(당사자)", receiptPage.status === 200);

// ── 9b. 영수증 생애주기(이행/분쟁) + 평판 v1 (R3) ──
console.log("9b. 영수증 이행/분쟁 + 평판 v1");
const rid = receipt.receiptId;

// 러너 receipts 엔드포인트 — founder 러너가 자기 거래 영수증을 가져간다 (OpenCrab ingest 데이터)
const runnerReceipts = await (
  await fetch(`${BASE}/api/runner/receipts`, { headers: founderRunner.headers })
).json();
ok("러너 receipts 엔드포인트가 영수증 제공", runnerReceipts.receipts.some((r) => r.id === rid));

// 평판 v1 API — 실행 데이터 기반 합성 신뢰점수
const rep0 = await admin.json(`/api/agents/${founderAgent.id}/reputation`);
ok("평판 v1 신뢰점수 계산됨", typeof rep0.reputation.trustScore === "number");
ok("평판 v1 거래수 반영", rep0.reputation.transactionCount >= 1);

const badAct = await admin.fetch(`/api/receipts/${rid}`, post({ action: "nope" }));
ok("영수증 잘못된 action 400", badAct.status === 400);

// 비당사자는 영수증 액션 불가
const stranger = new Session();
await stranger.login(`stranger-${suffix}@test.com`, "Stranger");
const strangerAct = await stranger.fetch(`/api/receipts/${rid}`, post({ action: "fulfill" }));
ok("비당사자 영수증 액션 403", strangerAct.status === 403);

// 이행 완료 (당사자) → 평판 이행률 반영
const fulfilled = await admin.json(`/api/receipts/${rid}`, post({ action: "fulfill", note: "배송 완료" }));
ok("영수증 이행 완료", fulfilled.status === "fulfilled");
const dblFulfill = await admin.fetch(`/api/receipts/${rid}`, post({ action: "fulfill" }));
ok("중복 이행 409", dblFulfill.status === 409);
const repF = await admin.json(`/api/agents/${founderAgent.id}/reputation`);
ok("평판 v1 이행률 100% 반영", repF.reputation.fulfillmentRate === 100);

// 분쟁 제기 (다른 당사자) — 이행 후에도 분쟁 가능, disputed는 종착 상태
const disputed = await alice.json(`/api/receipts/${rid}`, post({ action: "dispute", note: "조건 불일치" }));
ok("영수증 분쟁 제기", disputed.status === "disputed");
const afterDispute = await alice.fetch(`/api/receipts/${rid}`, post({ action: "fulfill" }));
ok("분쟁 후 전이 차단 409", afterDispute.status === 409);
const repD = await admin.json(`/api/agents/${founderAgent.id}/reputation`);
ok("평판 v1 분쟁률 100% 반영", repD.reputation.disputeRate === 100);

// ── 9c. 숙박 vertical: 조건표 + 이행 (R4) ──
console.log("9c. 숙박 조건표 + 이행 (R4)");
const lodgingRoom = await alice.json(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "trade" })
);
const lodgingIns = await alice.json(
  `/api/rooms/${lodgingRoom.roomId}/instructions`,
  post({ content: "1박 숙박을 5만원에 예약하고 싶다고 제안해" })
);
const li = (await aliceRunner.inbox()).instructions.find(
  (i) => i.instructionId === lodgingIns.instructionId
);
const lodgeHeld = await aliceRunner.reply({
  roomId: lodgingRoom.roomId,
  instructionId: li.instructionId,
  content: "1박 숙박을 5만원에 예약하고 싶습니다. 체크인은 다음 주 금요일입니다.",
  needsApproval: false,
});
ok("숙박 거래 제안 승인 대기", lodgeHeld.requiresApproval === true);
const lodgeView = await alice.json(`/api/rooms/${lodgingRoom.roomId}/messages`);
const lodgeMsg = lodgeView.messages.find((m) => m.content.includes("숙박"));
await alice.json(`/api/approvals/${lodgeMsg.approvalRequest.id}`, post({ decision: "approved" }));
const lodgeFounderView = await admin.json(`/api/rooms/${lodgingRoom.roomId}/messages`);
const lodgeProposal = lodgeFounderView.messages.find((m) => m.content.includes("숙박"));

// 잘못된 조건표는 400
const badCond = await admin.fetch(
  `/api/rooms/${lodgingRoom.roomId}/receipts`,
  post({ proposalMessageId: lodgeProposal.id, conditions: [{ value: "라벨 없음" }] })
);
ok("잘못된 조건표 400", badCond.status === 400);

// 숙박 조건표와 함께 확정
const lodgeReceipt = await admin.json(
  `/api/rooms/${lodgingRoom.roomId}/receipts`,
  post({
    proposalMessageId: lodgeProposal.id,
    conditions: [
      { label: "체크인 날짜", value: "다음 주 금요일" },
      { label: "인원", value: "2명" },
      { label: "총 가격", value: "50,000원" },
      { label: "취소 정책", value: "3일 전 무료" },
    ],
  })
);
ok("조건표와 함께 합의 확정", !!lodgeReceipt.receiptId);

const lodgeRunnerView = (
  await (await fetch(`${BASE}/api/runner/receipts`, { headers: founderRunner.headers })).json()
).receipts.find((r) => r.id === lodgeReceipt.receiptId);
ok("러너 receipts에 조건표 4건 포함", lodgeRunnerView?.conditions?.length === 4);

// 이행 완료 → 조건 met 기록
const lodgeFulfilled = await admin.json(
  `/api/receipts/${lodgeReceipt.receiptId}`,
  post({ action: "fulfill" })
);
ok("숙박 이행 완료", lodgeFulfilled.status === "fulfilled");
const lodgeAfter = (
  await (await fetch(`${BASE}/api/runner/receipts`, { headers: founderRunner.headers })).json()
).receipts.find((r) => r.id === lodgeReceipt.receiptId);
ok("이행 후 조건 met=true 기록", lodgeAfter?.conditions?.every((c) => c.met === true));

// ── 10. 지시 실패 보고 ──
console.log("10. 지시 실패 보고");
const failIns = await alice.json(
  `/api/rooms/${room.roomId}/instructions`,
  post({ content: "실패 테스트" })
);
const failRes = await fetch(`${BASE}/api/runner/instructions/${failIns.instructionId}/fail`, {
  method: "POST",
  headers: aliceRunner.headers,
  body: JSON.stringify({ error: "brain unavailable (test)" }),
});
ok("실패 보고 수락", failRes.ok);
const aliceView3 = await alice.json(`/api/rooms/${room.roomId}/messages`);
ok(
  "실패 지시 표시",
  aliceView3.instructions.find((i) => i.id === failIns.instructionId)?.status === "failed"
);

// ── 11. Rate limit (룸당 pending 5개) ──
console.log("11. 지시 rate limit");
const rlRoom = await alice.json(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "discussion" })
);
for (let i = 0; i < 5; i++) {
  await alice.json(`/api/rooms/${rlRoom.roomId}/instructions`, post({ content: `대기 지시 ${i + 1}` }));
}
const sixth = await alice.fetch(`/api/rooms/${rlRoom.roomId}/instructions`, post({ content: "6번째" }));
ok("룸당 pending 5개 초과 시 429", sixth.status === 429);

// ── 12. 룸 닫기 ──
console.log("12. 룸 닫기");
await alice.json(`/api/rooms/${rlRoom.roomId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ status: "closed" }),
});
const closedIns = await alice.fetch(`/api/rooms/${rlRoom.roomId}/instructions`, post({ content: "닫힌 룸 지시" }));
ok("닫힌 룸 지시 409", closedIns.status === 409);

// ── 12b. 회귀: 발견 API + 멱등성 (Phase 5 수정 검증) ──
console.log("12b. 발견 API + 멱등성 회귀");
const directory = await alice.json("/api/agents/directory");
ok("발견 API가 타 agent 노출", directory.agents.some((a) => a.id === founderAgent.id));
ok(
  "발견 API에 활동 신호(messagesSent) 포함",
  typeof directory.agents.find((a) => a.id === founderAgent.id)?.messagesSent === "number"
);
const dirSearch = await alice.json(`/api/agents/directory?q=${encodeURIComponent("founder")}`);
ok("발견 API 검색 동작", dirSearch.agents.some((a) => a.id === founderAgent.id));
const dirBadType = await alice.fetch("/api/agents/directory?type=garbage");
ok("발견 API 잘못된 type은 500 아님", dirBadType.status === 200);

// F2: 같은 지시 중복 수행 시 정확히 한 번만 성공 (TOCTOU 가드)
const idemRoom = await alice.json(
  "/api/rooms",
  post({ targetAgentId: founderAgent.id, initiatorAgentId: aliceAgent.id, type: "question" })
);
const idemIns = await alice.json(`/api/rooms/${idemRoom.roomId}/instructions`, post({ content: "멱등성 테스트" }));
const dup1 = aliceRunner.reply({ roomId: idemRoom.roomId, instructionId: idemIns.instructionId, content: "응답 A", needsApproval: false });
const dup2 = aliceRunner.reply({ roomId: idemRoom.roomId, instructionId: idemIns.instructionId, content: "응답 B", needsApproval: false });
const results = await Promise.allSettled([dup1, dup2]);
const succeeded = results.filter((r) => r.status === "fulfilled").length;
ok("동시 지시 수행은 정확히 1회만 성공", succeeded === 1);

// F4: 자기 메시지에 답장 시도 차단
const ownMsgView = await alice.json(`/api/rooms/${idemRoom.roomId}/messages`);
const myMsg = ownMsgView.messages.find((m) => m.senderAgentId === aliceAgent.id);
if (myMsg) {
  const selfReply = await fetch(`${BASE}/api/runner/messages`, {
    method: "POST",
    headers: aliceRunner.headers,
    body: JSON.stringify({ roomId: idemRoom.roomId, inReplyToId: myMsg.id, content: "x", needsApproval: false }),
  });
  ok("자기 메시지 답장 차단 400", selfReply.status === 400);
}

// ── 13. 알림 ──
console.log("13. 알림");
const aliceNotifs = await alice.json("/api/notifications");
ok(
  "승인 요청 알림 수신 (alice)",
  aliceNotifs.notifications.some((n) => n.kind === "approval_required")
);
ok(
  "거래 확정 알림 수신 (alice)",
  aliceNotifs.notifications.some((n) => n.kind === "receipt_created")
);
const adminNotifs = await admin.json("/api/notifications");
ok(
  "거래 확정 알림 수신 (founder)",
  adminNotifs.notifications.some((n) => n.kind === "receipt_created")
);
await alice.json("/api/notifications", { method: "POST" });
const afterRead = await alice.json("/api/notifications");
ok("모두 읽음 처리", afterRead.unread === 0);

console.log(`\n✅ 스모크 테스트 통과 — ${pass}개 검증`);
