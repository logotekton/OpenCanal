import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";

// 소유자가 밤 실행 하나의 상세를 조회한다: journal + 작업 + 산출물(리뷰 상태 포함).
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const run = await prisma.nightRun.findUnique({
    where: { id },
    include: {
      agent: { select: { id: true, handle: true, displayName: true } },
      tasks: { select: { id: true, title: true, brief: true, status: true } },
      artifacts: {
        orderBy: { createdAt: "asc" },
        select: {
          id: true,
          taskId: true,
          kind: true,
          title: true,
          content: true,
          review: true,
          reviewReason: true,
          reviewedAt: true,
        },
      },
    },
  });
  if (!run) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!(await userOwnsAgent(user.id, run.agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  return NextResponse.json({
    id: run.id,
    agent: run.agent,
    status: run.status,
    startedAt: run.startedAt.toISOString(),
    finishedAt: run.finishedAt?.toISOString() ?? null,
    error: run.error,
    journal: run.journal,
    tasks: run.tasks,
    artifacts: run.artifacts.map((a) => ({
      ...a,
      reviewedAt: a.reviewedAt?.toISOString() ?? null,
    })),
  });
}
