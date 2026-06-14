import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { capabilityDeclSchema } from "@opencanal/shared";

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

// 소유자가 수동 capability를 추가/갱신한다 (source=manual). 어댑터 동기화(source=adapter)와 공존.
export async function POST(req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const parsed = capabilityDeclSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "invalid capability" }, { status: 400 });
  const c = parsed.data;

  await prisma.agentCapability.upsert({
    where: { agentId_key: { agentId, key: c.key } },
    create: {
      agentId,
      key: c.key,
      label: c.label,
      description: c.description,
      requiresApproval: c.requiresApproval,
      source: "manual",
    },
    update: { label: c.label, description: c.description, requiresApproval: c.requiresApproval, enabled: true },
  });

  return NextResponse.json({ ok: true });
}

// 소유자가 수동 capability를 삭제한다 (어댑터 capability는 런타임 소관이라 건드리지 않는다).
export async function DELETE(req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const body = (await req.json().catch(() => ({}))) as { key?: string };
  if (!body.key) return NextResponse.json({ error: "key required" }, { status: 400 });

  await prisma.agentCapability.deleteMany({ where: { agentId, key: body.key, source: "manual" } });
  return NextResponse.json({ ok: true });
}
