import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { createRoomSchema } from "@opencanal/shared";

export async function POST(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = createRoomSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid input" }, { status: 400 });
  }
  const { targetAgentId, initiatorAgentId, type, title } = parsed.data;

  if (!(await userOwnsAgent(user.id, initiatorAgentId))) {
    return NextResponse.json({ error: "initiator agent is not yours" }, { status: 403 });
  }
  if (targetAgentId === initiatorAgentId) {
    return NextResponse.json({ error: "cannot open a room with yourself" }, { status: 400 });
  }

  const target = await prisma.agent.findUnique({ where: { id: targetAgentId } });
  if (!target) return NextResponse.json({ error: "target agent not found" }, { status: 404 });

  // "신원이 권한보다 먼저다" — 거래 룸은 양측 L1+ 그리고 개시 agent의 협상 권한이 켜져 있어야 한다
  if (type === "trade") {
    const initiator = await prisma.agent.findUnique({ where: { id: initiatorAgentId } });
    const levelOk = (lv: string) => lv !== "L0";
    if (!initiator || !levelOk(initiator.verificationLevel) || !levelOk(target.verificationLevel)) {
      return NextResponse.json(
        { error: "거래 룸은 양측 agent가 L1 이상이어야 합니다." },
        { status: 403 }
      );
    }
    const perms = initiator.permissions as { can_negotiate?: boolean } | null;
    if (!perms?.can_negotiate) {
      return NextResponse.json(
        { error: "거래 룸을 열려면 agent의 협상 권한(can_negotiate)을 먼저 켜야 합니다. 프로필 → 권한에서 설정하세요." },
        { status: 403 }
      );
    }
  }

  // Reuse an existing open room of the same type between the two agents (MVP: 1:1)
  const existing = await prisma.room.findFirst({
    where: {
      type,
      status: "open",
      AND: [
        { participants: { some: { agentId: initiatorAgentId } } },
        { participants: { some: { agentId: targetAgentId } } },
      ],
    },
  });
  if (existing) return NextResponse.json({ roomId: existing.id });

  const room = await prisma.room.create({
    data: {
      type,
      title,
      createdById: user.id,
      participants: {
        create: [
          { agentId: initiatorAgentId, role: "initiator" },
          { agentId: targetAgentId, role: "responder" },
        ],
      },
    },
  });

  return NextResponse.json({ roomId: room.id }, { status: 201 });
}
