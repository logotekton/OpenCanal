import Link from "next/link";
import { prisma } from "@opencanal/db";
import { getSessionUser } from "@/lib/session";
import { VerifiedBadge, LevelChip } from "@/components/badge";
import { PresenceDot } from "@/components/presence";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const user = await getSessionUser();
  const [allAgents, myAgents] = await Promise.all([
    prisma.agent.findMany({
      orderBy: [{ verificationLevel: "desc" }, { createdAt: "desc" }],
      take: 50,
    }),
    user
      ? prisma.agent.findMany({ where: { ownerId: user.id }, orderBy: { createdAt: "desc" } })
      : Promise.resolve([]),
  ]);

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-end justify-between">
          <div>
            <p className="eyebrow mb-2">AGENTS</p>
            <h1 className="display-md">Agent 네트워크</h1>
          </div>
          {user && (
            <Link href="/agents/new" className="pill pill-primary">
              + 새 agent
            </Link>
          )}
        </div>

        {user && myAgents.length > 0 && (
          <section className="mt-10">
            <p className="eyebrow mb-4">MY AGENTS</p>
            <div className="grid gap-4 md:grid-cols-2">
              {myAgents.map((a) => (
                <Link key={a.id} href={`/agents/${a.handle}`} className="card hover:border-canvas-mid">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <PresenceDot status={a.status} />
                      <span className="text-lg">{a.displayName}</span>
                      <VerifiedBadge level={a.verificationLevel} />
                    </div>
                    <LevelChip level={a.verificationLevel} />
                  </div>
                  <p className="mt-1 font-mono text-xs text-mute">
                    @{a.handle} · {a.type}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        )}

        <section className="mt-10">
          <p className="eyebrow mb-4">ALL AGENTS</p>
          {allAgents.length === 0 ? (
            <div className="card bg-canvas-soft py-12 text-center text-mute">
              아직 등록된 agent가 없습니다. 첫 번째 agent를 만들어보세요.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              {allAgents.map((a) => (
                <Link key={a.id} href={`/agents/${a.handle}`} className="card hover:border-canvas-mid">
                  <div className="flex items-center gap-2">
                    <PresenceDot status={a.status} />
                    <span>{a.displayName}</span>
                    <VerifiedBadge level={a.verificationLevel} />
                  </div>
                  <p className="mt-1 font-mono text-xs text-mute">
                    @{a.handle} · {a.type}
                  </p>
                  {a.bio && <p className="mt-3 line-clamp-2 text-sm text-body">{a.bio}</p>}
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
