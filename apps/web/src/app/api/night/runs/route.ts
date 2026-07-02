import { NextResponse } from "next/server";
import { Prisma, prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { apiUser } from "@/lib/session";
import { nightRunReportSchema } from "@opencanal/shared";

// 러너가 밤 실행 결과를 보고한다 (러너 인증). 트랜잭션으로 run + artifacts 생성,
// taskResults에 따라 NightTask 상태/runId를 갱신한다.
export async function POST(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = nightRunReportSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid report" }, { status: 400 });
  }
  const report = parsed.data;
  const agentId = device.agentId;

  const runId = await prisma.$transaction(async (tx) => {
    const run = await tx.nightRun.create({
      data: {
        agentId,
        status: report.status,
        startedAt: new Date(report.startedAt),
        finishedAt: new Date(report.finishedAt),
        error: report.error ?? null,
        journal: report.journal as unknown as Prisma.InputJsonValue,
      },
    });

    if (report.artifacts.length > 0) {
      await tx.nightArtifact.createMany({
        data: report.artifacts.map((a) => ({
          runId: run.id,
          taskId: a.taskId,
          agentId,
          kind: a.kind,
          title: a.title,
          content: a.content,
        })),
      });
    }

    for (const tr of report.taskResults) {
      await tx.nightTask.updateMany({
        where: { id: tr.taskId, agentId },
        data: { status: tr.status, runId: run.id },
      });
    }

    return run.id;
  });

  return NextResponse.json({ runId });
}

// 소유자가 내 agent들의 최근 밤 실행 목록을 조회한다 (산출물 수, 리뷰 대기 수 포함).
export async function GET() {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const agents = await prisma.agent.findMany({ where: { ownerId: user.id }, select: { id: true } });
  const agentIds = agents.map((a) => a.id);

  const runs = await prisma.nightRun.findMany({
    where: { agentId: { in: agentIds } },
    orderBy: { startedAt: "desc" },
    take: 20,
    include: {
      agent: { select: { id: true, handle: true, displayName: true } },
      _count: { select: { artifacts: true } },
    },
  });

  const runIds = runs.map((r) => r.id);
  const pendingGroups =
    runIds.length > 0
      ? await prisma.nightArtifact.groupBy({
          by: ["runId"],
          where: { runId: { in: runIds }, review: "pending" },
          _count: { _all: true },
        })
      : [];
  const pendingByRun = new Map(pendingGroups.map((g) => [g.runId, g._count._all]));

  return NextResponse.json({
    runs: runs.map((r) => ({
      id: r.id,
      agent: r.agent,
      status: r.status,
      startedAt: r.startedAt.toISOString(),
      finishedAt: r.finishedAt?.toISOString() ?? null,
      artifactCount: r._count.artifacts,
      pendingReviewCount: pendingByRun.get(r.id) ?? 0,
    })),
  });
}
