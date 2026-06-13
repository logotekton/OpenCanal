import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";

export async function POST(req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const body = (await req.json().catch(() => ({}))) as { note?: string; officialUrl?: string };

  const existing = await prisma.verificationRequest.findFirst({
    where: { agentId, state: "pending" },
  });
  if (existing) {
    return NextResponse.json({ error: "이미 심사 대기 중인 신청이 있습니다." }, { status: 409 });
  }

  const request = await prisma.verificationRequest.create({
    data: {
      agentId,
      requestedLevel: "L2",
      evidence: { note: body.note ?? "", officialUrl: body.officialUrl ?? "" },
    },
  });

  return NextResponse.json({ id: request.id }, { status: 201 });
}
