import { NextResponse } from "next/server";
import { prisma, Prisma } from "@opencanal/db";
import { generateDeviceToken, hashToken } from "@/lib/runner-auth";
import {
  provisionBodySchema,
  ACTIVE_PROVISION_SOURCES,
  originForSource,
  type ProvisionSource,
} from "@opencanal/shared";

// 외부 agent가 자기 정체성으로 OpenCanal 검증 agent를 프로비전한다 (페어링 + 생성 한 번에).
// 원칙(docs/CONNECT_PLAN.md): provenance ≠ verification — 여기서 L2+·배지는 절대 세팅하지 않는다
// (admin 경로 전용). verificationLevel L1 = 코드를 발급한 소유자의 이메일 검증 티어일 뿐.

// 트랜잭션 내 1회용 코드 원자적 소비 실패 신호 — throw로 전체 롤백(코드는 미소비로 보존되어 재시도 가능)
class GrantConflict extends Error {}
const isP2002 = (e: unknown) => !!e && typeof e === "object" && (e as { code?: string }).code === "P2002";

async function uniqueHandle(desired: string): Promise<string> {
  for (let i = 0; i < 50; i++) {
    const candidate = i === 0 ? desired : `${desired}-${i + 1}`.slice(0, 30);
    const exists = await prisma.agent.findUnique({ where: { handle: candidate }, select: { id: true } });
    if (!exists) return candidate;
  }
  return `${desired.slice(0, 24)}-${Math.random().toString(36).slice(2, 6)}`;
}

export async function POST(req: Request) {
  const parsed = provisionBodySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid payload" }, { status: 400 });
  }
  const { code, source, external, runnerVersion } = parsed.data;

  // Phase 1 게이트: opencrab(정체성, 두뇌 네이티브)만 활성. 외부 두뇌는 3원칙 강제 후(Phase 2).
  if (!ACTIVE_PROVISION_SOURCES.includes(source as ProvisionSource)) {
    return NextResponse.json({ error: `${source}는 아직 연결 준비 중입니다.` }, { status: 403 });
  }

  const grant = await prisma.provisionGrant.findUnique({ where: { code: code.trim().toUpperCase() } });
  if (!grant || grant.consumedAt || grant.expiresAt < new Date()) {
    return NextResponse.json({ error: "invalid or expired code" }, { status: 400 });
  }

  const origin = originForSource(source as ProvisionSource);
  const token = generateDeviceToken();

  const existingLink = await prisma.externalAgentLink.findUnique({
    where: { source_externalId: { source, externalId: external.externalId } },
    include: { agent: { select: { id: true, ownerId: true, handle: true } } },
  });
  // 다른 계정이 이미 이 외부 agent를 연결했으면 충돌 (멱등 키 도용 방지)
  if (existingLink && existingLink.agent.ownerId !== grant.userId) {
    return NextResponse.json({ error: "이 외부 agent는 다른 계정에 이미 연결되어 있습니다." }, { status: 409 });
  }

  // 트랜잭션 첫 단계에서 1회용 코드를 원자적으로 claim — count===0이면 이미 소비됨(동시 요청)
  const claimGrant = async (tx: Prisma.TransactionClient) => {
    const claim = await tx.provisionGrant.updateMany({
      where: { id: grant.id, consumedAt: null },
      data: { consumedAt: new Date() },
    });
    if (claim.count === 0) throw new GrantConflict();
  };

  let agentId: string;
  let handle: string;

  try {
    if (existingLink) {
      // 재연결 = 갱신. verificationLevel/배지는 건드리지 않는다(원칙 ①). 디바이스 토큰만 재발급.
      await prisma.$transaction(async (tx) => {
        await claimGrant(tx);
        await tx.agent.update({
          where: { id: existingLink.agentId },
          data: { displayName: external.displayName, bio: external.bio ?? null, type: external.type, origin },
        });
        await tx.runnerDevice.deleteMany({ where: { agentId: existingLink.agentId } });
        await tx.runnerDevice.create({
          data: { agentId: existingLink.agentId, tokenHash: hashToken(token), name: `connect:${source}`, runnerVersion: runnerVersion ?? null },
        });
      });
      agentId = existingLink.agentId;
      handle = existingLink.agent.handle;
    } else {
      handle = await uniqueHandle(external.handle);
      const created = await prisma.$transaction(async (tx) => {
        await claimGrant(tx);
        const a = await tx.agent.create({
          data: {
            ownerId: grant.userId,
            handle,
            displayName: external.displayName,
            bio: external.bio ?? null,
            type: external.type,
            origin,
            // L1 = 소유자 이메일 검증 티어(네이티브와 동일). L2+/배지는 admin만 — 출처로 부여 금지.
            verificationLevel: "L1",
            sources:
              source === "opencrab"
                ? {
                    create: {
                      kind: "opencrab_pack",
                      config: { packId: external.externalId, externalUrl: external.externalUrl },
                      status: "pending",
                    },
                  }
                : undefined,
            externalLink: { create: { source, externalId: external.externalId, externalUrl: external.externalUrl ?? null } },
          },
          select: { id: true },
        });
        await tx.runnerDevice.create({
          data: { agentId: a.id, tokenHash: hashToken(token), name: `connect:${source}`, runnerVersion: runnerVersion ?? null },
        });
        return a;
      });
      agentId = created.id;
    }
  } catch (err) {
    // 코드 동시 소비 → 409. 핸들/외부링크 unique 경합(P2002) → 409. (롤백되어 코드는 보존)
    if (err instanceof GrantConflict) {
      return NextResponse.json({ error: "invalid or expired code" }, { status: 409 });
    }
    if (isP2002(err)) {
      return NextResponse.json({ error: "핸들 또는 외부 agent가 동시에 연결되었습니다. 다시 시도하세요." }, { status: 409 });
    }
    throw err;
  }

  // 외부 skill → capability 동기화 (있으면). 어댑터 동기화(source=adapter)와 동일 의미.
  if (external.capabilities?.length) {
    await prisma.$transaction([
      prisma.agentCapability.deleteMany({ where: { agentId, source: "adapter" } }),
      prisma.agentCapability.createMany({
        data: external.capabilities.map((c) => ({
          agentId,
          key: c.key,
          label: c.label,
          description: c.description,
          requiresApproval: c.requiresApproval,
          source: "adapter",
        })),
        skipDuplicates: true,
      }),
    ]);
  }

  return NextResponse.json({ deviceToken: token, agentId, handle, origin });
}
