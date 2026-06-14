import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { z } from "zod";

// Intent 팬아웃 (ROOM_REDESIGN Bend 3): 한 Intent를 다수 responder가 든 N자 룸으로.
// RFQ/경매의 기반 — 한 의도를 여러 후보 agent에게 동시에 던진다. (trade는 게이트 복잡도로 Phase 후속)
const bodySchema = z.object({
  initiatorAgentId: z.string().min(1),
  targetAgentIds: z.array(z.string().min(1)).min(1).max(20),
  type: z.enum(["question", "discussion", "help"]).default("question"),
});

export async function POST(req: Request, { params }: { params: Promise<{ intentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { intentId } = await params;
  const parsed = bodySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const { initiatorAgentId, targetAgentIds, type } = parsed.data;

  const intent = await prisma.intent.findUnique({ where: { id: intentId }, select: { createdById: true } });
  if (!intent || intent.createdById !== user.id) {
    return NextResponse.json({ error: "intent not found" }, { status: 404 });
  }
  if (!(await userOwnsAgent(user.id, initiatorAgentId))) {
    return NextResponse.json({ error: "initiator agent is not yours" }, { status: 403 });
  }

  // 중복/자기 제외, 존재 검증
  const targets = [...new Set(targetAgentIds)].filter((id) => id !== initiatorAgentId);
  if (targets.length === 0) {
    return NextResponse.json({ error: "at least one distinct target required" }, { status: 400 });
  }
  const found = await prisma.agent.count({ where: { id: { in: targets } } });
  if (found !== targets.length) {
    return NextResponse.json({ error: "some target agents not found" }, { status: 404 });
  }

  const room = await prisma.room.create({
    data: {
      type,
      intentId,
      createdById: user.id,
      participants: {
        create: [
          { agentId: initiatorAgentId, role: "initiator" },
          ...targets.map((id) => ({ agentId: id, role: "responder" as const })),
        ],
      },
    },
    select: { id: true, _count: { select: { participants: true } } },
  });

  await prisma.intent.update({ where: { id: intentId }, data: { status: "in_session" } });

  return NextResponse.json(
    { roomId: room.id, intentId, participantCount: room._count.participants },
    { status: 201 }
  );
}
