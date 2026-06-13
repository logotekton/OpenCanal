import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";

// agent가 선언한 능력 목록 — 공개 신뢰 신호 ("이 agent가 무엇을 할 수 있는가").
export async function GET(_req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  const capabilities = await prisma.agentCapability.findMany({
    where: { agentId, enabled: true },
    orderBy: { createdAt: "asc" },
    select: { key: true, label: true, description: true, requiresApproval: true, source: true },
  });

  return NextResponse.json({ capabilities });
}
