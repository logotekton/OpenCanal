import { NextResponse } from "next/server";
import { prisma } from "@opencanal/db";
import { bridgeSecretOk } from "@/lib/bridge-auth";

// 브리지 워커가 폴링: 연결된 chat의 사용자에게 since 이후 생성된 알림을 chatId와 함께 반환한다.
// (승인 요청/거래 확정/이행/분쟁 등 → 텔레그램 푸시). 워커가 자체 커서(since)를 관리한다.
export async function GET(req: Request) {
  if (!bridgeSecretOk(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const since = new URL(req.url).searchParams.get("since");
  const sinceDate = since ? new Date(since) : new Date(Date.now() - 60_000);
  if (Number.isNaN(sinceDate.getTime())) {
    return NextResponse.json({ error: "invalid since" }, { status: 400 });
  }

  const links = await prisma.telegramLink.findMany({ select: { chatId: true, userId: true } });
  const chatByUser = new Map(links.map((l) => [l.userId, l.chatId]));
  if (chatByUser.size === 0) return NextResponse.json({ notifications: [] });

  const notifications = await prisma.notification.findMany({
    where: { userId: { in: [...chatByUser.keys()] }, createdAt: { gt: sinceDate } },
    orderBy: { createdAt: "asc" },
    take: 100,
  });

  // approval_required 알림은 인라인 승인/반려 버튼용 approvalId를 동봉한다 (href의 roomId로 역추적).
  const enriched = await Promise.all(
    notifications.map(async (n) => {
      let approvalId: string | null = null;
      if (n.kind === "approval_required") {
        const roomId = n.href?.match(/\/rooms\/([^/?#]+)/)?.[1];
        if (roomId) {
          const pending = await prisma.approvalRequest.findFirst({
            where: { state: "pending", agent: { ownerId: n.userId }, message: { roomId } },
            orderBy: { createdAt: "desc" },
            select: { id: true },
          });
          approvalId = pending?.id ?? null;
        }
      }
      return {
        chatId: chatByUser.get(n.userId),
        id: n.id,
        kind: n.kind,
        title: n.title,
        body: n.body,
        href: n.href,
        approvalId,
        createdAt: n.createdAt.toISOString(),
      };
    })
  );

  return NextResponse.json({ notifications: enriched });
}
