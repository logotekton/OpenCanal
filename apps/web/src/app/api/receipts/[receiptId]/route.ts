import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { notifyUser } from "@/lib/notify";

// 영수증 생애주기 전이 — 당사자(양측 소유자 중 한쪽)가 이행 완료/분쟁을 기록한다.
// 결제·자동거래는 없다(can_spend off 유지): fulfilled는 "조건이 지켜졌다"는 당사자 기록일 뿐.
// 평판 v1의 이행률/분쟁률이 이 전이로 계산된다.
export async function POST(req: Request, { params }: { params: Promise<{ receiptId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { receiptId } = await params;
  const body = (await req.json().catch(() => ({}))) as { action?: string; note?: string };
  if (body.action !== "fulfill" && body.action !== "dispute") {
    return NextResponse.json({ error: "action must be fulfill|dispute" }, { status: 400 });
  }
  const note = typeof body.note === "string" ? body.note.trim().slice(0, 1000) || null : null;

  const receipt = await prisma.contractReceipt.findUnique({
    where: { id: receiptId },
    include: {
      room: {
        include: {
          participants: { include: { agent: { select: { id: true, ownerId: true, handle: true } } } },
        },
      },
    },
  });
  if (!receipt) return NextResponse.json({ error: "receipt not found" }, { status: 404 });

  const myParticipant = receipt.room.participants.find((p) => p.agent.ownerId === user.id);
  if (!myParticipant) return NextResponse.json({ error: "forbidden" }, { status: 403 });

  // 전이 규칙: confirmed → fulfilled | disputed; fulfilled → disputed(이행 후에도 분쟁 가능).
  // disputed는 종착 상태 — 불변 분쟁 기록이므로 더 이상 전이하지 않는다.
  if (receipt.status === "disputed") {
    return NextResponse.json({ error: "이미 분쟁 중인 영수증입니다." }, { status: 409 });
  }
  if (body.action === "fulfill" && receipt.status === "fulfilled") {
    return NextResponse.json({ error: "이미 이행 완료된 영수증입니다." }, { status: 409 });
  }

  const updated = await prisma.contractReceipt.update({
    where: { id: receiptId },
    data:
      body.action === "fulfill"
        ? { status: "fulfilled", fulfilledAt: new Date(), note }
        : { status: "disputed", disputedAt: new Date(), note },
  });

  // 룸 시스템 메시지 + 상대 소유자 알림 (대리 구조의 신경)
  const label = body.action === "fulfill" ? "이행 완료로 표시되었습니다" : "분쟁이 제기되었습니다";
  await prisma.message.create({
    data: {
      roomId: receipt.roomId,
      senderAgentId: myParticipant.agentId,
      authorKind: "system",
      content: `합의 영수증 — ${label}.${note ? ` 사유: ${note}` : ""}`,
      status: "delivered",
    },
  });
  const kind = body.action === "fulfill" ? "receipt_fulfilled" : "receipt_disputed";
  const others = receipt.room.participants.filter((p) => p.agent.ownerId !== user.id);
  await Promise.all(
    others.map((p) =>
      notifyUser(p.agent.ownerId, kind, `합의 영수증 — ${label}`, {
        body: receipt.terms.slice(0, 100),
        href: `/receipts/${receipt.id}`,
      })
    )
  );

  return NextResponse.json({ ok: true, status: updated.status });
}
