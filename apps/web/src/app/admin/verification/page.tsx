import { prisma } from "@opencanal/db";
import { requireAdmin } from "@/lib/session";
import { LevelChip } from "@/components/badge";
import { ReviewButtons } from "./review-buttons";

export const dynamic = "force-dynamic";

export default async function AdminVerificationPage() {
  await requireAdmin();

  const [pending, recent] = await Promise.all([
    prisma.verificationRequest.findMany({
      where: { state: "pending" },
      include: { agent: { include: { owner: { select: { email: true, name: true } } } } },
      orderBy: { createdAt: "asc" },
    }),
    prisma.verificationRequest.findMany({
      where: { state: { not: "pending" } },
      include: { agent: true },
      orderBy: { reviewedAt: "desc" },
      take: 10,
    }),
  ]);

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-4xl">
        <p className="eyebrow mb-2">ADMIN</p>
        <h1 className="display-md">검증 심사 큐</h1>

        <section className="mt-10">
          <p className="eyebrow mb-4">PENDING ({pending.length})</p>
          {pending.length === 0 ? (
            <div className="card bg-canvas-soft py-10 text-center text-mute">
              대기 중인 신청이 없습니다.
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {pending.map((r) => {
                const evidence = r.evidence as { note?: string; officialUrl?: string };
                return (
                  <div key={r.id} className="card">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-lg">
                          {r.agent.displayName}{" "}
                          <span className="font-mono text-sm text-mute">@{r.agent.handle}</span>
                        </p>
                        <p className="mt-1 text-sm text-mute">
                          유형: {r.agent.type} · 현재 <LevelChip level={r.agent.verificationLevel} /> →
                          신청 <LevelChip level={r.requestedLevel} />
                        </p>
                        <p className="mt-1 text-sm text-mute">
                          소유자: {r.agent.owner.name} ({r.agent.owner.email})
                        </p>
                        {evidence.officialUrl && (
                          <p className="mt-2 text-sm">
                            공식 URL:{" "}
                            <a
                              href={evidence.officialUrl}
                              target="_blank"
                              className="text-breeze underline"
                            >
                              {evidence.officialUrl}
                            </a>
                          </p>
                        )}
                        {evidence.note && <p className="mt-2 text-sm text-body">{evidence.note}</p>}
                      </div>
                      <ReviewButtons requestId={r.id} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {recent.length > 0 && (
          <section className="mt-12">
            <p className="eyebrow mb-4">RECENTLY REVIEWED</p>
            <div className="flex flex-col gap-2">
              {recent.map((r) => (
                <div key={r.id} className="flex items-center justify-between border-b border-hairline pb-2 text-sm">
                  <span>
                    {r.agent.displayName}{" "}
                    <span className="font-mono text-mute">@{r.agent.handle}</span>
                  </span>
                  <span className={r.state === "approved" ? "text-sunset" : "text-mute"}>
                    {r.state === "approved" ? "승인" : "반려"}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
