import { prisma } from "@opencanal/db";
import { computeReputationV1, type ReputationV1, type Claim } from "@opencanal/shared";

// 평판 v1 집계 — 실행 데이터를 모아 순수 computeReputationV1로 환산한다.
// 신뢰 신호의 단일 출처: 프로필·디렉토리·평판 API가 모두 이걸 쓴다(같은 점수 보장).

/**
 * 여러 agent의 평판을 배치로 계산한다. agent 수와 무관하게 쿼리 수가 고정(6) — 디렉토리의 N+1 방지.
 * getAgentReputation은 이걸 위임한다(단일 출처).
 */
export async function getReputationsBatch(agentIds: string[]): Promise<Map<string, ReputationV1>> {
  const out = new Map<string, ReputationV1>();
  if (agentIds.length === 0) return out;
  const idSet = new Set(agentIds);

  const [parts, msgSent, apprs, receipts, claimRows] = await Promise.all([
    // 각 agent의 룸 참여 (응답률·영수증 집계용)
    prisma.roomParticipant.findMany({
      where: { agentId: { in: agentIds } },
      select: { agentId: true, roomId: true },
    }),
    // 보낸 메시지 수
    prisma.message.groupBy({
      by: ["senderAgentId"],
      where: { senderAgentId: { in: agentIds }, authorKind: "agent" },
      _count: true,
    }),
    // 소유자 결정이 끝난 승인요청 (승인률/반려율)
    prisma.approvalRequest.groupBy({
      by: ["agentId", "state"],
      where: { agentId: { in: agentIds }, state: { not: "pending" } },
      _count: true,
    }),
    // agent가 당사자인 영수증 (이행률/분쟁률)
    prisma.contractReceipt.findMany({
      where: { room: { participants: { some: { agentId: { in: agentIds } } } } },
      select: { status: true, room: { select: { participants: { select: { agentId: true } } } } },
    }),
    // 근거점수 표본 (MVP 규모에선 take 5000이 전체에 근접)
    prisma.message.findMany({
      where: { senderAgentId: { in: agentIds }, authorKind: "agent" },
      select: { senderAgentId: true, claims: true },
      take: 5000,
    }),
  ]);

  // 룸 → (우리 집합에 속한) 참여 agent들
  const roomToAgents = new Map<string, string[]>();
  for (const p of parts) {
    const arr = roomToAgents.get(p.roomId) ?? [];
    arr.push(p.agentId);
    roomToAgents.set(p.roomId, arr);
  }
  const roomIds = [...roomToAgents.keys()];

  // 응답률: 우리 agent들의 룸에 전달된(approval none|approved) 상대 메시지 vs answered
  const roomMsgs = roomIds.length
    ? await prisma.message.findMany({
        where: { roomId: { in: roomIds }, authorKind: "agent", approval: { in: ["none", "approved"] } },
        select: { roomId: true, senderAgentId: true, status: true },
      })
    : [];

  const zero = () => ({
    incomingTotal: 0,
    incomingAnswered: 0,
    approvalsDecided: 0,
    approvalsApproved: 0,
    receiptsTotal: 0,
    receiptsFulfilled: 0,
    receiptsDisputed: 0,
    messagesSent: 0,
    evidenceConsidered: 0,
    messagesWithEvidence: 0,
  });
  const acc = new Map(agentIds.map((id) => [id, zero()]));

  for (const m of roomMsgs) {
    for (const a of roomToAgents.get(m.roomId) ?? []) {
      if (a === m.senderAgentId) continue; // 자기 메시지는 incoming 아님
      const r = acc.get(a)!;
      r.incomingTotal++;
      if (m.status === "answered") r.incomingAnswered++;
    }
  }
  for (const g of msgSent) {
    const r = acc.get(g.senderAgentId);
    if (r) r.messagesSent = g._count;
  }
  for (const g of apprs) {
    const r = acc.get(g.agentId);
    if (!r) continue;
    r.approvalsDecided += g._count;
    if (g.state === "approved") r.approvalsApproved += g._count;
  }
  for (const rc of receipts) {
    for (const p of rc.room.participants) {
      if (!idSet.has(p.agentId)) continue;
      const r = acc.get(p.agentId)!;
      r.receiptsTotal++;
      if (rc.status === "fulfilled") r.receiptsFulfilled++;
      else if (rc.status === "disputed") r.receiptsDisputed++;
    }
  }
  for (const row of claimRows) {
    const r = acc.get(row.senderAgentId);
    if (!r) continue;
    r.evidenceConsidered++;
    const claims = Array.isArray(row.claims) ? (row.claims as Claim[]) : [];
    if (claims.some((c) => c.type === "evidence" || c.type === "responsibility")) {
      r.messagesWithEvidence++;
    }
  }

  for (const id of agentIds) out.set(id, computeReputationV1(acc.get(id)!));
  return out;
}

export async function getAgentReputation(agentId: string): Promise<ReputationV1> {
  const map = await getReputationsBatch([agentId]);
  return map.get(agentId)!;
}
