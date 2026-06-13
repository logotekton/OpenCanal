import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { permissionsSchema } from "@opencanal/shared";

// 소유자가 자기 agent의 권한(v1 Mandate 축약형)을 조정한다.
// can_speak/can_advise는 항상 켜져 있고, can_commit/can_spend는 MVP에서 켤 수 없다(자동 결제 금지선).
export async function PATCH(req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const body = (await req.json().catch(() => ({}))) as { can_negotiate?: boolean };
  if (typeof body.can_negotiate !== "boolean") {
    return NextResponse.json({ error: "can_negotiate boolean required" }, { status: 400 });
  }

  const agent = await prisma.agent.findUnique({ where: { id: agentId } });
  const current = permissionsSchema.parse(agent?.permissions ?? {});
  const next = { ...current, can_negotiate: body.can_negotiate, can_commit: false, can_spend: false };

  await prisma.agent.update({ where: { id: agentId }, data: { permissions: next } });
  return NextResponse.json({ permissions: next });
}
