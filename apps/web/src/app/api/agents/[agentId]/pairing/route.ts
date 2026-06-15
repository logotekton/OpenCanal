import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { generatePairingCode } from "@/lib/runner-auth";

export async function POST(_req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  // Invalidate previous unconsumed codes for this agent
  await prisma.devicePairing.deleteMany({ where: { agentId, consumedAt: null } });

  const pairing = await prisma.devicePairing.create({
    data: {
      agentId,
      code: generatePairingCode(),
      expiresAt: new Date(Date.now() + 10 * 60 * 1000),
    },
  });

  return NextResponse.json({ code: pairing.code, expiresAt: pairing.expiresAt }, { status: 201 });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  await prisma.runnerDevice.deleteMany({ where: { agentId } });
  await prisma.agent.update({ where: { id: agentId }, data: { status: "offline" } });

  return NextResponse.json({ ok: true });
}
