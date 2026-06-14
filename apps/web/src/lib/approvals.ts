import { prisma } from "@opencanal/db";
import { notifyGateway } from "@/lib/gateway";

// 승인/반려 결정의 단일 출처 — 웹 라우트(/api/approvals/[id])와 텔레그램 브리지가 공유한다.
// 결과는 {status, body}로 반환해 호출부가 그대로 응답하거나 봇 메시지로 변환한다.
export async function decideApproval(
  userId: string,
  approvalId: string,
  decision: "approved" | "rejected"
): Promise<{ status: number; body: Record<string, unknown> }> {
  const approval = await prisma.approvalRequest.findUnique({
    where: { id: approvalId },
    include: {
      agent: { select: { ownerId: true } },
      message: { include: { room: { include: { participants: true } } } },
    },
  });
  if (!approval || approval.state !== "pending") {
    return { status: 404, body: { error: "not found or already decided" } };
  }
  if (approval.agent.ownerId !== userId) {
    return { status: 403, body: { error: "forbidden" } };
  }

  const approved = decision === "approved";

  await prisma.$transaction([
    prisma.approvalRequest.update({
      where: { id: approvalId },
      data: { state: approved ? "approved" : "rejected", decidedAt: new Date() },
    }),
    prisma.message.update({
      where: { id: approval.messageId },
      data: {
        approval: approved ? "approved" : "rejected",
        // 승인되면 상대 러너 처리 대기(pending) 상태로 전달된다
        status: approved ? "pending" : "failed",
      },
    }),
  ]);

  if (approved) {
    // Bend 3: N자 — 승인된 메시지는 작성자를 제외한 모든 참여자에게 푸시
    const others = approval.message.room.participants.filter(
      (p) => p.agentId !== approval.message.senderAgentId
    );
    await Promise.all(
      others.map((p) =>
        notifyGateway({ kind: "room.message", targetAgentId: p.agentId, messageId: approval.messageId })
      )
    );
  }

  return { status: 200, body: { ok: true } };
}
