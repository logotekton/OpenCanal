import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";

// Recent delivered conversation window for prompt assembly (runner-side).
export async function GET(req: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { roomId } = await params;
  const participant = await prisma.roomParticipant.findUnique({
    where: { roomId_agentId: { roomId, agentId: device.agentId } },
  });
  if (!participant) return NextResponse.json({ error: "not in room" }, { status: 403 });

  const messages = await prisma.message.findMany({
    where: {
      roomId,
      approval: { in: ["none", "approved"] },
      status: { in: ["delivered", "answered"] },
    },
    include: { sender: { select: { handle: true } } },
    orderBy: { createdAt: "desc" },
    take: 20,
  });

  return NextResponse.json({
    messages: messages.reverse().map((m) => ({
      senderHandle: m.sender.handle,
      senderAgentId: m.senderAgentId,
      content: m.content,
      createdAt: m.createdAt.toISOString(),
    })),
  });
}
