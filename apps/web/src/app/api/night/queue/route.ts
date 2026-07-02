import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { nightQueueSchema, type NightQueue, type NightPolicyKind } from "@opencanal/shared";

// 러너가 밤 시작 시 큐를 pull한다: 활성 정책·지시, queued 작업(최대 5), 미ingest 반려(교정).
// 응답은 nightQueueSchema 계약으로 검증해서 내보낸다.
export async function GET(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const agentId = device.agentId;
  const [owner, policies, directives, tasks, corrections] = await Promise.all([
    prisma.agent.findUnique({
      where: { id: agentId },
      select: { owner: { select: { name: true } } },
    }),
    prisma.nightPolicy.findMany({ where: { agentId, active: true }, orderBy: { createdAt: "asc" } }),
    prisma.nightDirective.findMany({ where: { agentId, active: true }, orderBy: { createdAt: "asc" } }),
    prisma.nightTask.findMany({
      where: { agentId, status: "queued" },
      orderBy: { order: "asc" },
      take: 5,
    }),
    prisma.nightArtifact.findMany({
      where: { agentId, review: "rejected", correctionIngestedAt: null },
      include: { task: { select: { title: true } } },
      orderBy: { reviewedAt: "asc" },
    }),
  ]);

  const payload: NightQueue = {
    agent: { id: device.agent.id, handle: device.agent.handle, displayName: device.agent.displayName },
    ownerName: owner?.owner.name ?? null,
    policies: policies.map((p) => ({
      id: p.id,
      kind: p.kind as NightPolicyKind,
      text: p.text,
      active: p.active,
    })),
    directives: directives.map((d) => ({ id: d.id, content: d.content })),
    tasks: tasks.map((t) => ({
      id: t.id,
      title: t.title,
      brief: t.brief,
      originPolicyId: t.originPolicyId,
      originNote: t.originNote,
    })),
    corrections: corrections.map((a) => ({
      artifactId: a.id,
      artifactTitle: a.title,
      taskTitle: a.task?.title ?? null,
      reason: a.reviewReason ?? "",
      reviewedAt: (a.reviewedAt ?? a.createdAt).toISOString(),
    })),
  };

  return NextResponse.json(nightQueueSchema.parse(payload));
}
