import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { notifyGateway } from "@/lib/gateway";

// Owner approves/rejects their agent's held reply (trade rooms, commitment language).
export async function POST(req: Request, { params }: { params: Promise<{ approvalId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { approvalId } = await params;
  const body = (await req.json().catch(() => ({}))) as { decision?: string };
  if (body.decision !== "approved" && body.decision !== "rejected") {
    return NextResponse.json({ error: "decision must be approved|rejected" }, { status: 400 });
  }

  const approval = await prisma.approvalRequest.findUnique({
    where: { id: approvalId },
    include: {
      agent: { select: { ownerId: true } },
      message: { include: { room: { include: { participants: true } } } },
    },
  });
  if (!approval || approval.state !== "pending") {
    return NextResponse.json({ error: "not found or already decided" }, { status: 404 });
  }
  if (approval.agent.ownerId !== user.id) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const approved = body.decision === "approved";

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
    const counterpart = approval.message.room.participants.find(
      (p) => p.agentId !== approval.message.senderAgentId
    );
    if (counterpart) {
      await notifyGateway({
        kind: "room.message",
        targetAgentId: counterpart.agentId,
        messageId: approval.messageId,
      });
    }
  }

  return NextResponse.json({ ok: true });
}
