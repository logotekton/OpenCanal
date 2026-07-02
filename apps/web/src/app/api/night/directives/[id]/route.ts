import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { z } from "zod";

const patchSchema = z.object({
  content: z.string().min(1).optional(),
  active: z.boolean().optional(),
});

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const directive = await prisma.nightDirective.findUnique({ where: { id }, select: { agentId: true } });
  if (!directive) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!(await userOwnsAgent(user.id, directive.agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const parsed = patchSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }

  const updated = await prisma.nightDirective.update({ where: { id }, data: parsed.data });
  return NextResponse.json({ directive: updated });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const directive = await prisma.nightDirective.findUnique({ where: { id }, select: { agentId: true } });
  if (!directive) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!(await userOwnsAgent(user.id, directive.agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  await prisma.nightDirective.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}
