import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { z } from "zod";

// 검증 신청 페이로드 — 무제한 저장 방지 (빈 본문/초장문 거부)
const verificationSchema = z.object({
  note: z.string().min(1, "설명을 입력해주세요.").max(2000),
  officialUrl: z.string().url().max(500).optional().or(z.literal("")),
});

export async function POST(req: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { agentId } = await params;
  if (!(await userOwnsAgent(user.id, agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const parsed = verificationSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "invalid input" },
      { status: 400 }
    );
  }
  const body = parsed.data;

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
