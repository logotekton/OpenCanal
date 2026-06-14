import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { generateDeviceToken, hashToken } from "@/lib/runner-auth";

// Runner pairing: exchange a short-lived pairing code for a long-lived device token.
// 디바이스 토큰 원문은 이 응답에만 존재한다 — 서버는 해시만 저장.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    code?: string;
    deviceName?: string;
    runnerVersion?: string;
  };
  const code = (body.code ?? "").trim().toUpperCase();
  if (!code) return NextResponse.json({ error: "code required" }, { status: 400 });

  const pairing = await prisma.devicePairing.findUnique({
    where: { code },
    include: { agent: true },
  });
  if (!pairing || pairing.consumedAt || pairing.expiresAt < new Date()) {
    return NextResponse.json({ error: "invalid or expired code" }, { status: 400 });
  }

  const token = generateDeviceToken();

  await prisma.$transaction([
    prisma.devicePairing.update({
      where: { id: pairing.id },
      data: { consumedAt: new Date() },
    }),
    // One device per agent: replace any existing device
    prisma.runnerDevice.deleteMany({ where: { agentId: pairing.agentId } }),
    prisma.runnerDevice.create({
      data: {
        agentId: pairing.agentId,
        tokenHash: hashToken(token),
        name: body.deviceName ?? null,
        runnerVersion: body.runnerVersion ?? null,
      },
    }),
  ]);

  return NextResponse.json({
    deviceToken: token,
    agentId: pairing.agentId,
    handle: pairing.agent.handle,
    displayName: pairing.agent.displayName,
  });
}
