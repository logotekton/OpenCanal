import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { z } from "zod";

const patchSchema = z.object({
  title: z.string().min(1).optional(),
  brief: z.string().min(1).optional(),
  originNote: z.string().nullish(),
});

// queued 작업만 편집/삭제할 수 있다 (이미 집어간 카드는 실행 원장의 일부).
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const task = await prisma.nightTask.findUnique({ where: { id }, select: { agentId: true, status: true } });
  if (!task) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!(await userOwnsAgent(user.id, task.agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  if (task.status !== "queued") {
    return NextResponse.json({ error: "queued 작업만 편집할 수 있습니다." }, { status: 409 });
  }

  const parsed = patchSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const data = parsed.data;

  const updated = await prisma.nightTask.update({
    where: { id },
    data: {
      ...(data.title !== undefined ? { title: data.title } : {}),
      ...(data.brief !== undefined ? { brief: data.brief } : {}),
      ...(data.originNote !== undefined ? { originNote: data.originNote ?? null } : {}),
    },
  });
  return NextResponse.json({ task: updated });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const task = await prisma.nightTask.findUnique({ where: { id }, select: { agentId: true, status: true } });
  if (!task) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!(await userOwnsAgent(user.id, task.agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  if (task.status !== "queued") {
    return NextResponse.json({ error: "queued 작업만 삭제할 수 있습니다." }, { status: 409 });
  }

  await prisma.nightTask.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}
