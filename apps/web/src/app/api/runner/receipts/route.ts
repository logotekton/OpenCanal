import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";

// 러너가 자기 agent가 당사자인 확정 영수증을 가져가 OpenCrab(학습 메모리)에 ingest한다.
// ocm_ 토큰은 러너 로컬에만 있으므로 ingest는 러너에서 수행 — 플랫폼은 데이터만 제공한다.
export async function GET(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const rooms = await prisma.roomParticipant.findMany({
    where: { agentId: device.agentId },
    select: { roomId: true },
  });
  const roomIds = rooms.map((r) => r.roomId);

  const receipts = roomIds.length
    ? await prisma.contractReceipt.findMany({
        where: { roomId: { in: roomIds } },
        orderBy: { createdAt: "asc" },
        take: 200,
        include: {
          room: {
            select: {
              type: true,
              participants: {
                where: { agentId: { not: device.agentId } },
                select: { agent: { select: { handle: true } } },
              },
            },
          },
          proposal: { select: { sender: { select: { handle: true } } } },
        },
      })
    : [];

  return NextResponse.json({
    receipts: receipts.map((r) => ({
      id: r.id,
      roomId: r.roomId,
      roomType: r.room.type,
      status: r.status,
      terms: r.terms,
      transcriptHash: r.transcriptHash,
      counterpartHandle: r.room.participants[0]?.agent.handle ?? null,
      proposerHandle: r.proposal.sender.handle,
      createdAt: r.createdAt.toISOString(),
      fulfilledAt: r.fulfilledAt?.toISOString() ?? null,
      disputedAt: r.disputedAt?.toISOString() ?? null,
      conditions: Array.isArray(r.conditions) ? r.conditions : null,
    })),
  });
}
