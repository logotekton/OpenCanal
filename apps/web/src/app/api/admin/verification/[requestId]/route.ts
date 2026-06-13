import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { notifyUser } from "@/lib/notify";

export async function POST(req: Request, { params }: { params: Promise<{ requestId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (user.role !== "admin") return NextResponse.json({ error: "forbidden" }, { status: 403 });

  const { requestId } = await params;
  const body = (await req.json().catch(() => ({}))) as { decision?: string; note?: string };
  if (body.decision !== "approved" && body.decision !== "rejected") {
    return NextResponse.json({ error: "decision must be approved|rejected" }, { status: 400 });
  }

  const request = await prisma.verificationRequest.findUnique({
    where: { id: requestId },
    include: { agent: true },
  });
  if (!request || request.state !== "pending") {
    return NextResponse.json({ error: "request not found or already reviewed" }, { status: 404 });
  }

  if (body.decision === "approved") {
    await prisma.$transaction([
      prisma.verificationRequest.update({
        where: { id: requestId },
        data: { state: "approved", reviewerId: user.id, reviewedAt: new Date(), reviewNote: body.note },
      }),
      prisma.agent.update({
        where: { id: request.agentId },
        data: { verificationLevel: request.requestedLevel },
      }),
      prisma.verificationBadge.upsert({
        where: { agentId: request.agentId },
        create: {
          agentId: request.agentId,
          level: request.requestedLevel,
          kind: request.agent.type,
          approvedById: user.id,
          evidenceNote: body.note,
        },
        update: { level: request.requestedLevel, approvedById: user.id, approvedAt: new Date() },
      }),
    ]);
  } else {
    await prisma.verificationRequest.update({
      where: { id: requestId },
      data: { state: "rejected", reviewerId: user.id, reviewedAt: new Date(), reviewNote: body.note },
    });
  }

  await notifyUser(
    request.agent.ownerId,
    "verification_reviewed",
    body.decision === "approved"
      ? `@${request.agent.handle} 검증이 승인되었습니다 — 주황 딱지가 부여됩니다`
      : `@${request.agent.handle} 검증이 반려되었습니다`,
    { body: body.note, href: `/agents/${request.agent.handle}` }
  );

  return NextResponse.json({ ok: true });
}
