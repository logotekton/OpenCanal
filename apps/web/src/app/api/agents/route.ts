import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { createAgentSchema, manualProfileConfigSchema } from "@opencanal/shared";
import { z } from "zod";

const bodySchema = createAgentSchema.extend({
  sourceKind: z.enum(["opencrab_pack", "manual_profile", "none"]).default("none"),
  packId: z.string().optional(),
  tastes: z.string().optional(),
  hobbies: z.string().optional(),
  skills: z.string().optional(),
});

export async function POST(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = bodySchema.safeParse(await req.json());
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const { handle, displayName, type, bio, sourceKind, packId, tastes, hobbies, skills } = parsed.data;

  const existing = await prisma.agent.findUnique({ where: { handle } });
  if (existing) {
    return NextResponse.json({ error: `@${handle}은 이미 사용 중입니다.` }, { status: 409 });
  }

  if (sourceKind === "opencrab_pack" && !packId?.trim()) {
    return NextResponse.json({ error: "OpenCrab 팩 ID를 입력해주세요." }, { status: 400 });
  }

  let agent;
  try {
    agent = await prisma.agent.create({
      data: {
        ownerId: user.id,
        handle,
        displayName,
        type,
        bio,
        // 이메일 로그인 = 이메일 검증 완료 → L1. L0는 미인증 상태 예약, L2+는 관리자 딱지
        verificationLevel: "L1",
        sources:
          sourceKind === "opencrab_pack"
            ? { create: { kind: "opencrab_pack", config: { packId: packId!.trim() }, status: "pending" } }
            : sourceKind === "manual_profile"
              ? {
                  create: {
                    kind: "manual_profile",
                    config: manualProfileConfigSchema.parse({ tastes, hobbies, skills }),
                    status: "linked",
                  },
                }
              : undefined,
      },
    });
  } catch (err) {
    // 사전 findUnique를 통과한 동시 생성 경합 — unique 위반을 500이 아닌 409로
    if (err && typeof err === "object" && (err as { code?: string }).code === "P2002") {
      return NextResponse.json({ error: `@${handle}은 이미 사용 중입니다.` }, { status: 409 });
    }
    throw err;
  }

  return NextResponse.json({ id: agent.id, handle: agent.handle }, { status: 201 });
}

export async function GET() {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const agents = await prisma.agent.findMany({
    where: { ownerId: user.id },
    orderBy: { createdAt: "desc" },
  });
  return NextResponse.json({ agents });
}
