import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";

// 룸 닫기/다시 열기 — 참여 agent의 소유자만 가능
export async function PATCH(req: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { roomId } = await params;
  const body = (await req.json().catch(() => ({}))) as { status?: string };
  if (body.status !== "open" && body.status !== "closed") {
    return NextResponse.json({ error: "status must be open|closed" }, { status: 400 });
  }

  const room = await prisma.room.findUnique({
    where: { id: roomId },
    include: { participants: { include: { agent: { select: { ownerId: true } } } } },
  });
  if (!room) return NextResponse.json({ error: "room not found" }, { status: 404 });
  if (!room.participants.some((p) => p.agent.ownerId === user.id)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  await prisma.room.update({ where: { id: roomId }, data: { status: body.status } });
  return NextResponse.json({ ok: true, status: body.status });
}
