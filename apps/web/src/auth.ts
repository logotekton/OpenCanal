import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import { prisma } from "@opencanal/db";

// 인증 정책:
// - Google OAuth: AUTH_GOOGLE_ID/SECRET가 설정되면 활성화 (프로덕션 기본)
// - dev-email(비밀번호 없는 이메일 로그인): ALLOW_DEV_LOGIN=true일 때만 — 프로덕션에서 금지
// 신원 검증은 로그인이 아니라 딱지(VerificationBadge) 레이어가 담당한다.

const adminEmails = (process.env.ADMIN_EMAILS ?? "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

const allowDevLogin =
  process.env.ALLOW_DEV_LOGIN === "true" || process.env.NODE_ENV !== "production";

async function upsertUser(email: string, name?: string | null, image?: string | null) {
  const normalized = email.trim().toLowerCase();
  const isAdmin = adminEmails.includes(normalized);
  return prisma.user.upsert({
    where: { email: normalized },
    create: {
      email: normalized,
      name: name ?? normalized.split("@")[0],
      image: image ?? undefined,
      role: isAdmin ? "admin" : "user",
    },
    update: isAdmin ? { role: "admin" } : {},
  });
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt" },
  trustHost: true,
  providers: [
    ...(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET ? [Google] : []),
    ...(allowDevLogin
      ? [
          Credentials({
            id: "dev-email",
            name: "Email (dev)",
            credentials: {
              email: { label: "Email", type: "email" },
              name: { label: "Name", type: "text" },
            },
            async authorize(credentials) {
              const email = String(credentials?.email ?? "").trim().toLowerCase();
              if (!email || !email.includes("@")) return null;
              const name = String(credentials?.name ?? "").trim() || null;
              const user = await upsertUser(email, name);
              return { id: user.id, email: user.email, name: user.name, role: user.role };
            },
          }),
        ]
      : []),
  ],
  callbacks: {
    async jwt({ token, user, account }) {
      // OAuth 첫 로그인: DB user로 매핑 (provider id가 아니라 DB id를 세션에 싣는다)
      if (account?.provider === "google" && user?.email) {
        const dbUser = await upsertUser(user.email, user.name, user.image);
        token.userId = dbUser.id;
        token.role = dbUser.role;
      } else if (user) {
        token.userId = (user as { id: string }).id;
        token.role = (user as { role?: string }).role ?? "user";
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        (session.user as { id?: string }).id = token.userId as string;
        (session.user as { role?: string }).role = token.role as string;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
});

export const devLoginEnabled = allowDevLogin;
export const googleEnabled = Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);
