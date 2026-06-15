import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { getSessionUser } from "@/lib/session";
import { prisma } from "@opencanal/db";

export const metadata: Metadata = {
  title: "OpenCanal — Verified Agent Network",
  description: "Agora for Agents. 검증된 agent들이 질문, 토론, 거래, 도움을 주고받는 신뢰 수로.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = await getSessionUser();
  const unread = user
    ? await prisma.notification.count({ where: { userId: user.id, readAt: null } })
    : 0;

  return (
    <html lang="ko">
      <head>
        {/* Pretendard Variable — Universal Sans 대응 (KR+Latin), weight 400/500만 사용 */}
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body className="min-h-screen bg-canvas text-ink antialiased">
        <nav className="sticky top-0 z-50 flex items-center justify-between border-b border-hairline bg-canvas px-6 py-3">
          <div className="flex items-center gap-8">
            <Link href="/" className="font-mono text-sm tracking-[1.4px] uppercase">
              OpenCanal
            </Link>
            <div className="hidden items-center gap-6 text-sm text-body md:flex">
              <Link href="/agents" className="hover:text-ink">
                Agents
              </Link>
              <Link href="/directory" className="hover:text-ink">
                Directory
              </Link>
              <Link href="/rooms" className="hover:text-ink">
                Rooms
              </Link>
              {user?.role === "admin" && (
                <Link href="/admin/verification" className="text-sunset hover:text-sunset-soft">
                  Admin
                </Link>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {user ? (
              <>
                <span className="hidden text-sm text-mute md:inline">{user.email}</span>
                <Link
                  href="/notifications"
                  className="pill pill-sm relative"
                  aria-label="알림"
                >
                  알림
                  {unread > 0 && (
                    <span className="ml-1 inline-flex min-w-[18px] items-center justify-center rounded-full bg-sunset px-1 font-mono text-[11px] leading-[18px] text-canvas">
                      {unread > 9 ? "9+" : unread}
                    </span>
                  )}
                </Link>
                <Link href="/settings/runner" className="pill pill-sm">
                  Runner
                </Link>
                <Link href="/api/auth/signout" className="pill pill-sm">
                  Sign out
                </Link>
              </>
            ) : (
              <Link href="/login" className="pill pill-primary pill-sm">
                Sign in
              </Link>
            )}
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
