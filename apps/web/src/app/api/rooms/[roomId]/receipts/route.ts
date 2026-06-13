import { NextResponse } from "next/server";
import { createHash } from "crypto";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { notifyUser } from "@/lib/notify";

// 합의 확정: 거래 룸에서 "상대 agent의 승인된 제안"을 제안받은 쪽 소유자가 확정한다.
// → ContractReceipt 생성 (transcript hash 포함, 불변 기록)
export async function POST(req: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { roomId } = await params;
  const body = (await req.json().catch(() => ({}))) as { proposalMessageId?: string };
  if (!body.proposalMessageId) {
    return NextResponse.json({ error: "proposalMessageId required" }, { status: 400 });
  }

  const room = await prisma.room.findUnique({
    where: { id: roomId },
    include: { participants: { include: { agent: { select: { id: true, ownerId: true, handle: true } } } } },
  });
  if (!room) return NextResponse.json({ error: "room not found" }, { status: 404 });
  if (room.type !== "trade") {
    return NextResponse.json({ error: "합의 확정은 거래 룸에서만 가능합니다." }, { status: 400 });
  }

  const myParticipant = room.participants.find((p) => p.agent.ownerId === user.id);
  if (!myParticipant) return NextResponse.json({ error: "forbidden" }, { status: 403 });

  const proposal = await prisma.message.findUnique({
    where: { id: body.proposalMessageId },
    include: { sender: { select: { id: true, ownerId: true, handle: true } }, receipt: true },
  });
  if (!proposal || proposal.roomId !== roomId) {
    return NextResponse.json({ error: "proposal not found" }, { status: 404 });
  }
  if (proposal.receipt) {
    return NextResponse.json({ error: "이미 확정된 제안입니다." }, { status: 409 });
  }
  // 내 agent가 보낸 제안을 내가 확정할 수는 없다 — 상대의 제안만
  if (proposal.sender.ownerId === user.id) {
    return NextResponse.json({ error: "상대의 제안만 확정할 수 있습니다." }, { status: 403 });
  }
  // 거래 룸 메시지는 승인을 거쳐야 전달되므로, 확정 가능한 제안 = approved 상태
  if (proposal.approval !== "approved") {
    return NextResponse.json({ error: "승인되어 전달된 제안만 확정할 수 있습니다." }, { status: 400 });
  }

  // transcript hash: 확정 시점까지 전달된 대화의 불변 지문
  // F7: createdAt 동률 시 흔들리지 않도록 id를 보조 정렬키로 — 해시 결정성 보장
  const delivered = await prisma.message.findMany({
    where: { roomId, approval: { in: ["none", "approved"] }, createdAt: { lte: proposal.createdAt } },
    orderBy: [{ createdAt: "asc" }, { id: "asc" }],
    select: { id: true, senderAgentId: true, content: true, createdAt: true },
  });
  const transcriptHash = createHash("sha256")
    .update(JSON.stringify(delivered))
    .digest("hex");

  // F6: proposalMessageId unique 위반(동시 확정)이 500으로 새지 않도록 409로 변환
  let receipt;
  try {
    receipt = await prisma.contractReceipt.create({
      data: {
        roomId,
        proposalMessageId: proposal.id,
        acceptedById: user.id,
        transcriptHash,
        terms: proposal.content,
      },
    });
  } catch (err) {
    if (err && typeof err === "object" && (err as { code?: string }).code === "P2002") {
      return NextResponse.json({ error: "이미 확정된 제안입니다." }, { status: 409 });
    }
    throw err;
  }

  // 룸에 시스템 메시지 + 양측 소유자 알림
  await prisma.message.create({
    data: {
      roomId,
      senderAgentId: myParticipant.agentId,
      authorKind: "system",
      content: `합의가 확정되었습니다. Receipt: ${receipt.id}`,
      status: "delivered",
    },
  });
  const counterpartOwner = proposal.sender.ownerId;
  await Promise.all([
    notifyUser(user.id, "receipt_created", "거래 합의를 확정했습니다", {
      body: proposal.content.slice(0, 100),
      href: `/receipts/${receipt.id}`,
    }),
    notifyUser(counterpartOwner, "receipt_created", `@${proposal.sender.handle}의 제안이 확정되었습니다`, {
      body: proposal.content.slice(0, 100),
      href: `/receipts/${receipt.id}`,
    }),
  ]);

  return NextResponse.json({ receiptId: receipt.id }, { status: 201 });
}
