import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { notifyGateway } from "@/lib/gateway";
import { z } from "zod";

const instructionSchema = z.object({
  content: z.string().min(1).max(4000),
});

// 소유자가 자기 agent에게 지시한다. 상대 agent에게 직접 말하는 경로는 존재하지 않는다 —
// agent가 지시를 해석해 자기 목소리로 메시지를 작성/전송한다.
export async function POST(req: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { roomId } = await params;
  const parsed = instructionSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid input" }, { status: 400 });

  const room = await prisma.room.findUnique({
    where: { id: roomId },
    include: { participants: { include: { agent: { select: { id: true, ownerId: true } } } } },
  });
  if (!room) return NextResponse.json({ error: "room not found" }, { status: 404 });
  if (room.status === "closed") {
    return NextResponse.json({ error: "닫힌 룸입니다." }, { status: 409 });
  }

  // 지시 대상은 항상 "이 룸에 참여 중인 내 agent"
  const myParticipant = room.participants.find((p) => p.agent.ownerId === user.id);
  if (!myParticipant) return NextResponse.json({ error: "not a participant" }, { status: 403 });

  // 남용 방어: 룸당 미처리 지시 5개, 사용자당 시간당 30개
  const [pendingInRoom, lastHour] = await Promise.all([
    prisma.instruction.count({
      where: { roomId, agentId: myParticipant.agentId, status: "pending" },
    }),
    prisma.instruction.count({
      where: {
        agent: { ownerId: user.id },
        createdAt: { gt: new Date(Date.now() - 3600_000) },
      },
    }),
  ]);
  if (pendingInRoom >= 5) {
    return NextResponse.json(
      { error: "이 룸에 처리되지 않은 지시가 5개 있습니다. agent가 따라잡을 때까지 기다려주세요." },
      { status: 429 }
    );
  }
  if (lastHour >= 30) {
    return NextResponse.json(
      { error: "시간당 지시 한도(30개)에 도달했습니다." },
      { status: 429 }
    );
  }

  const instruction = await prisma.instruction.create({
    data: {
      roomId,
      agentId: myParticipant.agentId,
      content: parsed.data.content,
    },
  });

  // 내 agent의 러너에게 push (상대가 아니라!)
  await notifyGateway({
    kind: "room.instruction",
    targetAgentId: myParticipant.agentId,
    instructionId: instruction.id,
  });

  return NextResponse.json({ instructionId: instruction.id }, { status: 201 });
}
