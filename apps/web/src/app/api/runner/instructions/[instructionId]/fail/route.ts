import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { notifyUser } from "@/lib/notify";

// Runner reports an instruction it could not execute (brain error 등) —
// 소유자가 룸에서 실패 사유를 보고 다시 지시할 수 있게 한다.
export async function POST(req: Request, { params }: { params: Promise<{ instructionId: string }> }) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { instructionId } = await params;
  const body = (await req.json().catch(() => ({}))) as { error?: string };

  const instruction = await prisma.instruction.findUnique({ where: { id: instructionId } });
  if (!instruction || instruction.agentId !== device.agentId) {
    return NextResponse.json({ error: "instruction not found" }, { status: 404 });
  }

  // 원자적 claim — pending인 동안 단 한 번만 실패 처리되도록 (runner/messages와 동일 패턴).
  // 동시 fail 호출 / fail+처리 경합에서 중복 알림·상태 덮어쓰기 방지.
  const claim = await prisma.instruction.updateMany({
    where: { id: instructionId, status: "pending" },
    data: { status: "failed", error: (body.error ?? "unknown error").slice(0, 500), processedAt: new Date() },
  });
  if (claim.count === 0) {
    return NextResponse.json({ error: "already processed" }, { status: 409 });
  }

  await notifyUser(
    device.agent.ownerId,
    "instruction_failed",
    `@${device.agent.handle}이(가) 지시를 수행하지 못했습니다`,
    { body: instruction.content.slice(0, 100), href: `/rooms/${instruction.roomId}` }
  );

  return NextResponse.json({ ok: true });
}
