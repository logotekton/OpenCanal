import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { notifyGateway } from "@/lib/gateway";
import { notifyUser } from "@/lib/notify";
import { brainOutputSchema } from "@opencanal/shared";
import { z } from "zod";

const replySchema = z
  .object({
    roomId: z.string(),
    inReplyToId: z.string().optional(), // 상대 메시지 자동응답
    instructionId: z.string().optional(), // 소유자 지시 수행
    content: z.string().min(1).max(16000),
    claims: brainOutputSchema.shape.claims,
    needsApproval: z.boolean().default(false),
  })
  .refine((v) => v.inReplyToId || v.instructionId, {
    message: "inReplyToId or instructionId required",
  });

// Runner posts its agent's message — either an auto-reply or an owner-instructed message.
// trade 룸이거나 needs_approval이면 인간 승인 대기.
export async function POST(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = replySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid payload" }, { status: 400 });
  }
  const { roomId, inReplyToId, instructionId, content, claims, needsApproval } = parsed.data;

  const participant = await prisma.roomParticipant.findUnique({
    where: { roomId_agentId: { roomId, agentId: device.agentId } },
    include: { room: { include: { participants: true } } },
  });
  if (!participant) return NextResponse.json({ error: "not in room" }, { status: 403 });
  if (participant.room.status === "closed") {
    return NextResponse.json({ error: "room closed" }, { status: 409 });
  }

  // 소유권/존재 사전 검증 (친절한 404/400). 경합 안전성은 아래 트랜잭션의 원자적 claim이 보장.
  if (instructionId) {
    const instruction = await prisma.instruction.findUnique({
      where: { id: instructionId },
      select: { agentId: true, roomId: true },
    });
    if (!instruction || instruction.agentId !== device.agentId || instruction.roomId !== roomId) {
      return NextResponse.json({ error: "instruction not found" }, { status: 404 });
    }
  }
  if (inReplyToId) {
    // F4: 답장 대상이 이 룸의 메시지이고, 내가 보낸 것이 아닌지(=상대 메시지) 검증
    const target = await prisma.message.findUnique({
      where: { id: inReplyToId },
      select: { roomId: true, senderAgentId: true },
    });
    if (!target || target.roomId !== roomId) {
      return NextResponse.json({ error: "reply target not found in room" }, { status: 404 });
    }
    if (target.senderAgentId === device.agentId) {
      return NextResponse.json({ error: "cannot reply to your own message" }, { status: 400 });
    }
  }

  const room = participant.room;
  const requiresApproval = needsApproval || room.type === "trade";

  // F2/F3: 메시지 생성 + 지시/답장 claim을 한 트랜잭션에서 원자적으로.
  // updateMany({where:{status:"pending"}})로 단 한 번만 성공하도록 보장 — 동시 유입(WS push +
  // inbox 드레인)에 대한 멱등성. count===0이면 이미 처리된 것이므로 전체 롤백 후 409.
  let conflict = false;
  let messageId: string | null = null;
  await prisma.$transaction(async (tx) => {
    if (instructionId) {
      const claim = await tx.instruction.updateMany({
        where: { id: instructionId, agentId: device.agentId, roomId, status: "pending" },
        data: { status: "processed", processedAt: new Date() },
      });
      if (claim.count === 0) {
        conflict = true;
        return;
      }
    }
    if (inReplyToId) {
      const claim = await tx.message.updateMany({
        where: { id: inReplyToId, roomId, senderAgentId: { not: device.agentId }, status: "pending" },
        data: { status: "answered" },
      });
      if (claim.count === 0) {
        conflict = true;
        return;
      }
    }
    const created = await tx.message.create({
      data: {
        roomId,
        senderAgentId: device.agentId,
        authorKind: "agent",
        content,
        claims: claims ?? undefined,
        inReplyToId,
        status: "pending",
        approval: requiresApproval ? "required" : "none",
        approvalRequest: requiresApproval
          ? { create: { agentId: device.agentId, summary: content.slice(0, 200) } }
          : undefined,
      },
      select: { id: true },
    });
    if (instructionId) {
      await tx.instruction.update({
        where: { id: instructionId },
        data: { resultMessageId: created.id },
      });
    }
    messageId = created.id;
  });

  if (conflict || !messageId) {
    return NextResponse.json(
      { error: "already processed (instruction or reply target)" },
      { status: 409 }
    );
  }

  if (!requiresApproval) {
    const counterpart = room.participants.find((p) => p.agentId !== device.agentId);
    if (counterpart) {
      await notifyGateway({
        kind: "room.message",
        targetAgentId: counterpart.agentId,
        messageId,
      });
    }
  } else {
    // 승인 대기 — 소유자에게 알림 (대리 구조의 신경)
    await notifyUser(
      device.agent.ownerId,
      "approval_required",
      `@${device.agent.handle}의 메시지가 승인을 기다립니다`,
      { body: content.slice(0, 100), href: `/rooms/${roomId}` }
    );
  }

  return NextResponse.json({ messageId, requiresApproval }, { status: 201 });
}
