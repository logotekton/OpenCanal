import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { generatePairingCode } from "@/lib/runner-auth";

// 소유자가 외부 agent 연결 코드를 발급한다 (provision-by-connection, docs/CONNECT_PLAN.md).
// 어댑터가 이 코드로 /api/connect/provision을 호출해 자기 정체성으로 OpenCanal agent를 만든다.
export async function POST() {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  // 한 번에 하나만 유효 — 이전 미사용 코드 정리
  await prisma.provisionGrant.deleteMany({ where: { userId: user.id, consumedAt: null } });

  const grant = await prisma.provisionGrant.create({
    data: { userId: user.id, code: generatePairingCode(), expiresAt: new Date(Date.now() + 10 * 60 * 1000) },
  });

  return NextResponse.json({ code: grant.code, expiresAt: grant.expiresAt }, { status: 201 });
}
