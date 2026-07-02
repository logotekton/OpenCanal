import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { authenticateRunner } from "@/lib/runner-auth";
import { correctionAckSchema } from "@opencanal/shared";

// 러너가 반려(교정)를 팩으로 재ingest한 뒤 ack한다 — 해당 agent 소유 artifact만 correctionIngestedAt 세팅.
export async function POST(req: Request) {
  const device = await authenticateRunner(req);
  if (!device) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const parsed = correctionAckSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "invalid input" }, { status: 400 });
  }

  const result = await prisma.nightArtifact.updateMany({
    where: {
      id: { in: parsed.data.artifactIds },
      agentId: device.agentId,
      review: "rejected",
      correctionIngestedAt: null,
    },
    data: { correctionIngestedAt: new Date() },
  });

  return NextResponse.json({ acked: result.count });
}
