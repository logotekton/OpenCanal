import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { z } from "zod";

// 상시 지시 CRUD (소유자). agentId는 GET=쿼리, POST=바디.
export async function GET(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const agentId = new URL(req.url).searchParams.get("agentId");
  if (!agentId) return NextResponse.json({ error: "agentId required" }, { status: 400 });
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const directives = await prisma.nightDirective.findMany({
    where: { agentId },
    orderBy: { createdAt: "asc" },
  });
  return NextResponse.json({ directives });
}

const createSchema = z.object({
  agentId: z.string().min(1),
  content: z.string().min(1),
});

export async function POST(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = createSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const { agentId, content } = parsed.data;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const directive = await prisma.nightDirective.create({ data: { agentId, content } });
  return NextResponse.json({ directive }, { status: 201 });
}
