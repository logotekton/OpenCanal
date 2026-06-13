import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { getAgentReputation } from "@/lib/reputation";

// 평판 v1 (실행 데이터 기반). 신뢰 신호이므로 로그인 사용자에게 공개 — 비밀/소유자 정보는 없다.
export async function GET(_req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  const agent = await prisma.agent.findUnique({ where: { id: agentId }, select: { id: true } });
  if (!agent) return NextResponse.json({ error: "agent not found" }, { status: 404 });

  const reputation = await getAgentReputation(agentId);
  return NextResponse.json({ reputation });
}
