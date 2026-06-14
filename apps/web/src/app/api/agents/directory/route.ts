import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser } from "@/lib/session";
import { getReputationsBatch } from "@/lib/reputation";

// F9: agent 발견(discovery) — 룸을 열려면 상대 agent의 id가 필요한데
// GET /api/agents는 본인 것만 반환했다. 공개 디렉토리로 그 갭을 메운다.
// 검증된(L2+) agent와 검색어 매칭을 우선 노출, 비밀/소유자 정보는 제외.
export async function GET(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const q = (url.searchParams.get("q") ?? "").trim().slice(0, 80);
  // 잘못된 enum 값이 Prisma where로 들어가 500이 나지 않도록 화이트리스트 검증
  const AGENT_TYPES = ["personal", "business", "enterprise", "government", "expert"] as const;
  const rawType = url.searchParams.get("type");
  const type = AGENT_TYPES.includes(rawType as never) ? rawType : null;

  const agents = await prisma.agent.findMany({
    where: {
      ...(q
        ? {
            OR: [
              { handle: { contains: q, mode: "insensitive" } },
              { displayName: { contains: q, mode: "insensitive" } },
            ],
          }
        : {}),
      ...(type ? { type: type as never } : {}),
    },
    orderBy: [{ verificationLevel: "desc" }, { createdAt: "desc" }],
    take: 50,
    select: {
      id: true,
      handle: true,
      displayName: true,
      type: true,
      status: true,
      verificationLevel: true,
      bio: true,
    },
  });

  // 발견 단계 신뢰 힌트 — 실행 기반 신뢰점수 + 확정 거래 + 활동. 배치 집계라 N+1 없음.
  const ids = agents.map((a) => a.id);
  const reps = await getReputationsBatch(ids);

  return NextResponse.json({
    agents: agents.map((a) => {
      const rep = reps.get(a.id);
      return {
        ...a,
        messagesSent: rep?.messagesSent ?? 0,
        trustScore: rep?.trustScore ?? null,
        transactionCount: rep?.transactionCount ?? 0,
      };
    }),
  });
}
