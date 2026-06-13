import Link from "next/link";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { MarkAllRead } from "./mark-all-read";

export const dynamic = "force-dynamic";

const KIND_LABELS: Record<string, string> = {
  approval_required: "승인 필요",
  instruction_failed: "지시 실패",
  verification_reviewed: "검증 결과",
  receipt_created: "거래 확정",
};

export default async function NotificationsPage() {
  const user = await requireUser();
  const notifications = await prisma.notification.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
    take: 50,
  });

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-2xl">
        <div className="flex items-end justify-between">
          <div>
            <p className="eyebrow mb-2">NOTIFICATIONS</p>
            <h1 className="display-md">알림</h1>
          </div>
          <MarkAllRead />
        </div>

        {notifications.length === 0 ? (
          <div className="card mt-8 bg-canvas-soft py-12 text-center text-mute">
            알림이 없습니다.
          </div>
        ) : (
          <div className="mt-8 flex flex-col gap-2">
            {notifications.map((n) => {
              const inner = (
                <div
                  className={`card flex items-start justify-between gap-4 ${
                    n.readAt ? "opacity-60" : "border-canvas-mid"
                  }`}
                >
                  <div>
                    <p className="text-sm">
                      <span
                        className={`mr-2 font-mono text-[11px] tracking-wider uppercase ${
                          n.kind === "approval_required" || n.kind === "receipt_created"
                            ? "text-sunset"
                            : "text-mute"
                        }`}
                      >
                        {KIND_LABELS[n.kind] ?? n.kind}
                      </span>
                      {n.title}
                    </p>
                    {n.body && <p className="mt-1 text-sm text-mute">{n.body}</p>}
                  </div>
                  <span className="shrink-0 text-xs text-mute">
                    {n.createdAt.toLocaleString("ko-KR")}
                  </span>
                </div>
              );
              return n.href ? (
                <Link key={n.id} href={n.href}>
                  {inner}
                </Link>
              ) : (
                <div key={n.id}>{inner}</div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
