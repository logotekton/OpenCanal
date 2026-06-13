import { prisma } from "@opencanal/db";

export type NotificationKind =
  | "approval_required"
  | "instruction_failed"
  | "verification_reviewed"
  | "receipt_created";

export async function notifyUser(
  userId: string,
  kind: NotificationKind,
  title: string,
  options?: { body?: string; href?: string }
): Promise<void> {
  try {
    await prisma.notification.create({
      data: { userId, kind, title, body: options?.body, href: options?.href },
    });
  } catch (err) {
    // 알림 실패가 본 동작을 막으면 안 된다
    console.error("[notify] failed:", err);
  }
}
