import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { z } from "zod";

// 작업 카드 백로그 CRUD (소유자). 생성 시 status=queued, order는 뒤에 붙인다.
export async function GET(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const agentId = new URL(req.url).searchParams.get("agentId");
  if (!agentId) return NextResponse.json({ error: "agentId required" }, { status: 400 });
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const tasks = await prisma.nightTask.findMany({
    where: { agentId },
    orderBy: [{ status: "asc" }, { order: "asc" }],
  });
  return NextResponse.json({ tasks });
}

const createSchema = z.object({
  agentId: z.string().min(1),
  title: z.string().min(1),
  brief: z.string().min(1),
  originNote: z.string().nullish(),
});

export async function POST(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = createSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const { agentId, title, brief, originNote } = parsed.data;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const last = await prisma.nightTask.findFirst({
    where: { agentId },
    orderBy: { order: "desc" },
    select: { order: true },
  });

  const task = await prisma.nightTask.create({
    data: {
      agentId,
      title,
      brief,
      originNote: originNote ?? null,
      status: "queued",
      order: (last?.order ?? -1) + 1,
    },
  });
  return NextResponse.json({ task }, { status: 201 });
}
