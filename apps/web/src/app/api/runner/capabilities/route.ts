import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { capabilitiesSyncSchema } from "@opencanal/shared";

// 어댑터 런타임 skill → OpenCanal capability 매핑 (R5).
// 외부 런타임(Moltbot/Hermes 등)이 자기 skill 목록을 동기화한다. source=adapter로만 교체하고
// 소유자가 수동 설정한 capability(source=manual)는 보존한다. 멱등 — 재동기화 시 누적되지 않는다.
export async function PUT(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = capabilitiesSyncSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid capabilities" }, { status: 400 });
  }
  const { capabilities } = parsed.data;

  await prisma.$transaction([
    prisma.agentCapability.deleteMany({ where: { agentId: device.agentId, source: "adapter" } }),
    prisma.agentCapability.createMany({
      data: capabilities.map((c) => ({
        agentId: device.agentId,
        key: c.key,
        label: c.label,
        description: c.description,
        requiresApproval: c.requiresApproval,
        source: "adapter",
      })),
      // 소유자 수동 capability와 key가 겹치면 건너뛴다 (unique [agentId,key])
      skipDuplicates: true,
    }),
  ]);

  return NextResponse.json({ ok: true, count: capabilities.length });
}
