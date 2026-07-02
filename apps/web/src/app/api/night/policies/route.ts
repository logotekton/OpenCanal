import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { NIGHT_POLICY_KINDS } from "@opencanal/shared";
import { z } from "zod";

// 판단 정책 CRUD (소유자). agentId는 GET=쿼리, POST=바디.
export async function GET(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const agentId = new URL(req.url).searchParams.get("agentId");
  if (!agentId) return NextResponse.json({ error: "agentId required" }, { status: 400 });
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const policies = await prisma.nightPolicy.findMany({
    where: { agentId },
    orderBy: [{ kind: "asc" }, { createdAt: "asc" }],
  });
  return NextResponse.json({ policies });
}

const createSchema = z.object({
  agentId: z.string().min(1),
  kind: z.enum(NIGHT_POLICY_KINDS),
  text: z.string().min(1),
});

export async function POST(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = createSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const { agentId, kind, text } = parsed.data;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const policy = await prisma.nightPolicy.create({ data: { agentId, kind, text } });
  return NextResponse.json({ policy }, { status: 201 });
}
