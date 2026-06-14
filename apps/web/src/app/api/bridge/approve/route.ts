import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { bridgeSecretOk } from "@/lib/bridge-auth";
import { decideApproval } from "@/lib/approvals";

// 브리지 워커가 호출: 텔레그램 인라인 버튼(승인/반려)을 chatId의 소유자 대리로 적용한다.
export async function POST(req: Request) {
  if (!bridgeSecretOk(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as {
    chatId?: string | number;
    approvalId?: string;
    decision?: string;
  };
  const chatId = body.chatId != null ? String(body.chatId) : "";
  if (!chatId || !body.approvalId) {
    return NextResponse.json({ error: "chatId and approvalId required" }, { status: 400 });
  }
  if (body.decision !== "approved" && body.decision !== "rejected") {
    return NextResponse.json({ error: "decision must be approved|rejected" }, { status: 400 });
  }

  const link = await prisma.telegramLink.findUnique({ where: { chatId } });
  if (!link) return NextResponse.json({ error: "chat not linked" }, { status: 404 });

  const { status, body: result } = await decideApproval(link.userId, body.approvalId, body.decision);
  return NextResponse.json(result, { status });
}
