import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { z } from "zod";

// F8: attest 본문 스키마 검증 (이전엔 무검증 캐스팅)
const attestSchema = z.object({
  packId: z.string().min(1).max(200).optional(),
  tenantId: z.string().max(200).optional(),
  manifestHash: z.string().max(200).optional(),
  nodeCount: z.number().int().nonnegative().optional(),
  spaces: z.array(z.string().max(100)).max(100).optional(),
});

// Runner attests an OpenCrab source link after validating the ocm_ token locally.
// 토큰 자체는 절대 전송되지 않는다 — 비밀이 아닌 메타데이터만.
export async function POST(req: Request, { params }: { params: Promise<{ sourceId: string }> }) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { sourceId } = await params;
  const source = await prisma.agentSource.findUnique({ where: { id: sourceId } });
  if (!source || source.agentId !== device.agentId) {
    return NextResponse.json({ error: "source not found" }, { status: 404 });
  }

  const parsed = attestSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid attest payload" }, { status: 400 });
  }
  const body = parsed.data;
  const prevConfig = (source.config ?? {}) as Record<string, unknown>;

  const updated = await prisma.agentSource.update({
    where: { id: sourceId },
    data: {
      status: "linked",
      config: {
        ...prevConfig,
        packId: body.packId ?? (typeof prevConfig.packId === "string" ? prevConfig.packId : undefined),
        tenantId: body.tenantId,
        manifestHash: body.manifestHash,
        nodeCount: body.nodeCount,
        spaces: body.spaces,
        attestedAt: new Date().toISOString(),
      } as Record<string, unknown> as never,
    },
  });

  return NextResponse.json({ ok: true, status: updated.status });
}
