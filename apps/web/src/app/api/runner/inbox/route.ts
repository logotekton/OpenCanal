import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";

// Runner drain: pending counterpart messages + pending owner instructions (all rooms).
export async function GET(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const rooms = await prisma.roomParticipant.findMany({
    where: { agentId: device.agentId },
    select: { roomId: true },
  });
  const roomIds = rooms.map((r) => r.roomId);

  const [messages, instructions, sources, capabilities] = await Promise.all([
    prisma.message.findMany({
      where: {
        roomId: { in: roomIds },
        senderAgentId: { not: device.agentId },
        status: "pending",
        approval: { in: ["none", "approved"] },
      },
      include: {
        room: { select: { type: true } },
        sender: { select: { id: true, handle: true, type: true, verificationLevel: true } },
      },
      orderBy: { createdAt: "asc" },
      take: 100,
    }),
    prisma.instruction.findMany({
      where: { agentId: device.agentId, status: "pending" },
      include: {
        room: {
          select: {
            type: true,
            participants: {
              where: { agentId: { not: device.agentId } },
              select: {
                agent: { select: { id: true, handle: true, type: true, verificationLevel: true } },
              },
            },
          },
        },
      },
      orderBy: { createdAt: "asc" },
      take: 100,
    }),
    prisma.agentSource.findMany({
      where: { agentId: device.agentId },
      select: { id: true, kind: true, config: true, status: true },
    }),
    prisma.agentCapability.findMany({
      where: { agentId: device.agentId, enabled: true },
      select: { key: true, label: true, description: true, requiresApproval: true },
    }),
  ]);

  return NextResponse.json({
    agentId: device.agentId,
    sources,
    capabilities,
    messages: messages.map((m) => ({
      type: "room.message" as const,
      roomId: m.roomId,
      roomType: m.room.type,
      messageId: m.id,
      senderAgentId: m.sender.id,
      senderHandle: m.sender.handle,
      senderAgentType: m.sender.type,
      senderVerificationLevel: m.sender.verificationLevel,
      content: m.content,
      createdAt: m.createdAt.toISOString(),
    })),
    instructions: instructions.map((i) => {
      const counterpart = i.room.participants[0]?.agent ?? null;
      return {
        type: "room.instruction" as const,
        roomId: i.roomId,
        roomType: i.room.type,
        instructionId: i.id,
        content: i.content,
        counterpart: counterpart
          ? {
              agentId: counterpart.id,
              handle: counterpart.handle,
              agentType: counterpart.type,
              verificationLevel: counterpart.verificationLevel,
            }
          : null,
        createdAt: i.createdAt.toISOString(),
      };
    }),
  });
}
