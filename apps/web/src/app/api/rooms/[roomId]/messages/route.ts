import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";

// 직접 메시지 전송 경로는 없다 — 사용자는 자기 agent에게만 지시한다.
// (POST는 /api/rooms/[roomId]/instructions 로 대체됨)

export async function GET(req: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { roomId } = await params;
  const room = await prisma.room.findUnique({
    where: { id: roomId },
    include: { participants: { include: { agent: { select: { id: true, ownerId: true } } } } },
  });
  if (!room) return NextResponse.json({ error: "room not found" }, { status: 404 });

  const myParticipant = room.participants.find((p) => p.agent.ownerId === user.id);
  if (!myParticipant) return NextResponse.json({ error: "forbidden" }, { status: 403 });

  const [messages, instructions] = await Promise.all([
    prisma.message.findMany({
      where: {
        roomId,
        // 승인 대기/반려된 메시지는 상대에게 보이지 않음 — 작성자 소유자에게만
        OR: [{ approval: { in: ["none", "approved"] } }, { sender: { ownerId: user.id } }],
      },
      include: {
        sender: { select: { handle: true, displayName: true, ownerId: true } },
        approvalRequest: { select: { id: true, state: true } },
        receipt: { select: { id: true } },
      },
      orderBy: { createdAt: "asc" },
      take: 200,
    }),
    // 지시는 본인 것만 — 상대에게는 절대 노출되지 않는 사적 채널
    prisma.instruction.findMany({
      where: { roomId, agentId: myParticipant.agentId },
      orderBy: { createdAt: "asc" },
      take: 100,
    }),
  ]);

  return NextResponse.json({ messages, instructions, myAgentId: myParticipant.agentId });
}
