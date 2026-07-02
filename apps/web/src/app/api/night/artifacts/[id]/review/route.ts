import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { apiUser, userOwnsAgent } from "@/lib/session";
import { reviewInputSchema } from "@opencanal/shared";

// 아침 리뷰: 소유자가 산출물을 승인/반려한다. 반려 사유는 팩 교정의 원료(provenance).
// 이미 리뷰된(pending 아님) 산출물의 재리뷰는 409.
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await apiUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  const parsed = reviewInputSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }

  const artifact = await prisma.nightArtifact.findUnique({
    where: { id },
    select: { agentId: true, review: true },
  });
  if (!artifact) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!(await userOwnsAgent(user.id, artifact.agentId))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  if (artifact.review !== "pending") {
    return NextResponse.json({ error: "이미 리뷰된 산출물입니다." }, { status: 409 });
  }

  const { decision, reason } = parsed.data;
  await prisma.nightArtifact.update({
    where: { id },
    data: {
      review: decision,
      reviewReason: decision === "rejected" ? reason!.trim() : null,
      reviewedById: user.id,
      reviewedAt: new Date(),
    },
  });

  return NextResponse.json({ ok: true });
}
