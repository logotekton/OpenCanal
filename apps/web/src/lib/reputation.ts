import { prisma } from "@opencanal/db";
import { computeReputationV1, type ReputationV1, type Claim } from "@opencanal/shared";

// 평판 v1 집계 — 실행 데이터를 모아 순수 computeReputationV1로 환산한다.
// 신뢰 신호의 단일 출처: 프로필·디렉토리·평판 API·러너 ingest가 모두 이걸 쓴다.
export async function getAgentReputation(agentId: string): Promise<ReputationV1> {
  const inAgentRooms = { room: { participants: { some: { agentId } } } } as const;

  const [
    incomingTotal,
    incomingAnswered,
    approvalsDecided,
    approvalsApproved,
    messagesSent,
    receiptsTotal,
    receiptsFulfilled,
    receiptsDisputed,
    sentClaimRows,
  ] = await Promise.all([
    // 응답률: agent에게 전달된(approval none|approved) 상대 메시지 vs 그중 answered
    prisma.message.count({
      where: { ...inAgentRooms, senderAgentId: { not: agentId }, authorKind: "agent", approval: { in: ["none", "approved"] } },
    }),
    prisma.message.count({
      where: { ...inAgentRooms, senderAgentId: { not: agentId }, authorKind: "agent", approval: { in: ["none", "approved"] }, status: "answered" },
    }),
    prisma.approvalRequest.count({ where: { agentId, state: { not: "pending" } } }),
    prisma.approvalRequest.count({ where: { agentId, state: "approved" } }),
    prisma.message.count({ where: { senderAgentId: agentId, authorKind: "agent" } }),
    prisma.contractReceipt.count({ where: inAgentRooms }),
    prisma.contractReceipt.count({ where: { ...inAgentRooms, status: "fulfilled" } }),
    prisma.contractReceipt.count({ where: { ...inAgentRooms, status: "disputed" } }),
    // 근거점수 표본: agent가 보낸 메시지의 claims (MVP 규모에선 take 2000이 전체에 근접)
    prisma.message.findMany({
      where: { senderAgentId: agentId, authorKind: "agent" },
      select: { claims: true },
      take: 2000,
    }),
  ]);

  const evidenceConsidered = sentClaimRows.length;
  const messagesWithEvidence = sentClaimRows.filter((m) => {
    // claims는 Json — 쓰기 경로는 배열|null만 저장하지만, 비배열 값이 와도 터지지 않도록 방어
    const claims = Array.isArray(m.claims) ? (m.claims as Claim[]) : [];
    return claims.some((c) => c.type === "evidence" || c.type === "responsibility");
  }).length;

  return computeReputationV1({
    incomingTotal,
    incomingAnswered,
    approvalsDecided,
    approvalsApproved,
    receiptsTotal,
    receiptsFulfilled,
    receiptsDisputed,
    messagesSent,
    evidenceConsidered,
    messagesWithEvidence,
  });
}
