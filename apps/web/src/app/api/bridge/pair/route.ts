import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { bridgeSecretOk } from "@/lib/bridge-auth";

// 브리지 워커가 호출: 사용자가 봇에 입력한 코드 + 텔레그램 chatId를 연결한다.
export async function POST(req: Request) {
  if (!bridgeSecretOk(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as { code?: string; chatId?: string | number };
  const code = typeof body.code === "string" ? body.code.trim().toUpperCase() : "";
  const chatId = body.chatId != null ? String(body.chatId) : "";
  if (!code || !chatId) {
    return NextResponse.json({ error: "code and chatId required" }, { status: 400 });
  }

  const pairing = await prisma.bridgePairing.findUnique({ where: { code } });
  if (!pairing || pairing.consumedAt || pairing.expiresAt < new Date()) {
    return NextResponse.json({ error: "invalid or expired code" }, { status: 400 });
  }

  // 코드 소비 + chatId→user 연결 (재페어링 시 chatId의 소유자 갱신)
  await prisma.$transaction([
    prisma.bridgePairing.update({ where: { id: pairing.id }, data: { consumedAt: new Date() } }),
    prisma.telegramLink.upsert({
      where: { chatId },
      create: { chatId, userId: pairing.userId },
      update: { userId: pairing.userId },
    }),
  ]);

  return NextResponse.json({ ok: true });
}
