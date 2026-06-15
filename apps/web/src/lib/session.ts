import { auth } from "@/auth";
import { prisma } from "@opencanal/db";
import { redirect } from "next/navigation";

export interface SessionUser {
  id: string;
  email: string;
  name: string | null;
  role: "user" | "admin";
}

export async function getSessionUser(): Promise<SessionUser | null> {
  const session = await auth();
  const u = session?.user as (SessionUser & { id?: string }) | undefined;
  if (!u?.id) return null;
  return { id: u.id, email: u.email ?? "", name: u.name ?? null, role: (u.role as "user" | "admin") ?? "user" };
}

export async function requireUser(): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  return user;
}

export async function requireAdmin(): Promise<SessionUser> {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  return user;
}

/** API route guard — returns null (caller should 401) instead of redirecting. */
export async function apiUser(): Promise<SessionUser | null> {
  return getSessionUser();
}

export async function userOwnsAgent(userId: string, agentId: string): Promise<boolean> {
  const agent = await prisma.agent.findUnique({ where: { id: agentId }, select: { ownerId: true } });
  return agent?.ownerId === userId;
}
