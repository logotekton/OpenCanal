import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { createIntentSchema } from "@opencanal/shared";

// Intent (ROOM_REDESIGN Bend 2): 소유자가 자기 agent를 통해 원하는 것. 룸/세션이 이를 이행한다.
export async function POST(req: Request) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = createIntentSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }
  const { onBehalfOfId, kind, spec } = parsed.data;

  if (!(await userOwnsAgent(user.id, onBehalfOfId))) {
    return NextResponse.json({ error: "on-behalf-of agent is not yours" }, { status: 403 });
  }

  const intent = await prisma.intent.create({
    data: { createdById: user.id, onBehalfOfId, kind, spec },
    select: { id: true, kind: true, status: true },
  });
  return NextResponse.json({ intent }, { status: 201 });
}

export async function GET() {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const intents = await prisma.intent.findMany({
    where: { createdById: user.id },
    orderBy: { createdAt: "desc" },
    take: 100,
  });
  return NextResponse.json({ intents });
}
