import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { generatePairingCode } from "@/lib/runner-auth";

// 소유자가 텔레그램 연결 코드를 발급한다. 봇에 `/pair <code>` 입력 → 브리지가 /api/bridge/pair 호출.
export async function POST() {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  // 이전 미사용 코드 정리 (한 번에 하나만 유효)
  await prisma.bridgePairing.deleteMany({ where: { userId: user.id, consumedAt: null } });

  const pairing = await prisma.bridgePairing.create({
    data: {
      userId: user.id,
      code: generatePairingCode(),
      expiresAt: new Date(Date.now() + 10 * 60 * 1000),
    },
  });

  return NextResponse.json({ code: pairing.code, expiresAt: pairing.expiresAt }, { status: 201 });
}
