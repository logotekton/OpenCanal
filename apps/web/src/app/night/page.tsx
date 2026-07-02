import Link from "next/link";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { journalEntrySchema, type JournalEntry } from "@opencanal/shared";
import { ReviewActions } from "./review-actions";

export const dynamic = "force-dynamic";

const JOURNAL_KIND_LABEL: Record<string, string> = {
  plan: "계획",
  produce: "생산",
  decision: "판단",
  correction: "교정",
  note: "메모",
};

const TASK_STATUS_LABEL: Record<string, string> = {
  queued: "대기",
  running: "진행",
  produced: "산출",
  skipped: "건너뜀",
  failed: "실패",
};

const REVIEW_LABEL: Record<string, string> = {
  pending: "리뷰 대기",
  approved: "승인됨",
  rejected: "반려됨",
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default async function NightPage({
  searchParams,
}: {
  searchParams: Promise<{ agent?: string; run?: string }>;
}) {
  const user = await requireUser();
  const sp = await searchParams;

  const agents = await prisma.agent.findMany({
    where: { ownerId: user.id },
    orderBy: { createdAt: "asc" },
    select: { id: true, handle: true, displayName: true },
  });

  if (agents.length === 0) {
    return (
      <main className="px-6 py-12">
        <div className="mx-auto max-w-2xl">
          <p className="eyebrow mb-2">NIGHT</p>
          <h1 className="display-md">밤사이 일지</h1>
          <div className="card mt-8 bg-canvas-soft py-12 text-center text-mute">
            먼저 <Link href="/agents/new" className="text-sunset">agent를 만들면</Link> 밤 루프를 시작할 수 있습니다.
          </div>
        </div>
      </main>
    );
  }

  const selectedAgent = agents.find((a) => a.id === sp.agent) ?? agents[0];

  const runs = await prisma.nightRun.findMany({
    where: { agentId: selectedAgent.id },
    orderBy: { startedAt: "desc" },
    take: 20,
    include: { _count: { select: { artifacts: true } } },
  });

  const pendingGroups =
    runs.length > 0
      ? await prisma.nightArtifact.groupBy({
          by: ["runId"],
          where: { runId: { in: runs.map((r) => r.id) }, review: "pending" },
          _count: { _all: true },
        })
      : [];
  const pendingByRun = new Map(pendingGroups.map((g) => [g.runId, g._count._all]));

  const selectedRun = runs.find((r) => r.id === sp.run) ?? runs[0] ?? null;

  const [detail, policies] = selectedRun
    ? await Promise.all([
        prisma.nightRun.findUnique({
          where: { id: selectedRun.id },
          include: {
            tasks: { select: { id: true, title: true, status: true } },
            artifacts: {
              orderBy: { createdAt: "asc" },
              include: { task: { select: { title: true } } },
            },
          },
        }),
        prisma.nightPolicy.findMany({
          where: { agentId: selectedAgent.id },
          select: { id: true, text: true },
        }),
      ])
    : [null, []];

  const policyText = new Map(policies.map((p) => [p.id, p.text]));

  const journal: JournalEntry[] = detail
    ? journalEntrySchema.array().safeParse(detail.journal).data ?? []
    : [];

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-4xl">
        <p className="eyebrow mb-2">NIGHT · 아침 리뷰</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h1 className="display-md">밤사이 일지</h1>
          <Link href="/night/plan" className="pill pill-sm">
            밤 계획 편집
          </Link>
        </div>

        {agents.length > 1 && (
          <div className="mt-6 flex flex-wrap gap-2">
            {agents.map((a) => (
              <Link
                key={a.id}
                href={`/night?agent=${a.id}`}
                className={`pill pill-sm ${a.id === selectedAgent.id ? "pill-primary" : ""}`}
              >
                {a.displayName}
              </Link>
            ))}
          </div>
        )}

        <div className="mt-8 grid gap-6 md:grid-cols-[240px_1fr]">
          {/* 실행 목록 */}
          <aside className="flex flex-col gap-2">
            <p className="eyebrow mb-1">최근 밤 실행</p>
            {runs.length === 0 && (
              <div className="card bg-canvas-soft py-8 text-center text-sm text-mute">
                아직 밤 실행이 없습니다.
              </div>
            )}
            {runs.map((r) => {
              const pending = pendingByRun.get(r.id) ?? 0;
              const active = selectedRun?.id === r.id;
              return (
                <Link
                  key={r.id}
                  href={`/night?agent=${selectedAgent.id}&run=${r.id}`}
                  className={`card px-4 py-3 ${active ? "border-canvas-mid" : "hover:border-canvas-mid"}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm">{fmtTime(r.startedAt.toISOString())}</span>
                    <span
                      className={`font-mono text-[11px] uppercase ${
                        r.status === "failed" ? "text-sunset" : "text-mute"
                      }`}
                    >
                      {r.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-mute">
                    산출물 {r._count.artifacts}
                    {pending > 0 && <span className="ml-2 text-sunset">리뷰 {pending}</span>}
                  </p>
                </Link>
              );
            })}
          </aside>

          {/* 실행 상세 */}
          <section className="min-w-0">
            {!detail ? (
              <div className="card bg-canvas-soft py-12 text-center text-mute">
                밤 실행을 선택하세요.
              </div>
            ) : (
              <>
                {detail.error && (
                  <div className="card mb-6 border-sunset/40 bg-canvas-soft text-sm text-sunset-soft">
                    실행 오류: {detail.error}
                  </div>
                )}

                {/* 밤사이 일지 타임라인 */}
                <div className="card">
                  <p className="eyebrow mb-4">밤사이 일지</p>
                  {journal.length === 0 ? (
                    <p className="text-sm text-mute">기록된 일지가 없습니다.</p>
                  ) : (
                    <ol className="flex flex-col gap-4">
                      {journal.map((e, i) => (
                        <li key={i} className="flex gap-3">
                          <div className="flex flex-col items-center">
                            <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-canvas-mid" />
                            {i < journal.length - 1 && <span className="mt-1 w-px flex-1 bg-hairline" />}
                          </div>
                          <div className="min-w-0 flex-1 pb-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-[11px] tracking-wider text-mute uppercase">
                                {fmtTime(e.at)}
                              </span>
                              <span
                                className={`rounded-full border px-2 py-0.5 font-mono text-[10px] tracking-wider uppercase ${
                                  e.kind === "correction"
                                    ? "border-sunset/50 text-sunset"
                                    : "border-hairline text-body"
                                }`}
                              >
                                {JOURNAL_KIND_LABEL[e.kind] ?? e.kind}
                              </span>
                              {e.policyId && (
                                <span
                                  className="rounded-full bg-canvas-soft px-2 py-0.5 font-mono text-[10px] text-breeze"
                                  title={policyText.get(e.policyId) ?? "정책 원문 없음"}
                                >
                                  [P:{e.policyId.slice(0, 6)}]
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-sm text-body">{e.text}</p>
                            {e.policyId && policyText.has(e.policyId) && (
                              <p className="mt-1 text-xs text-mute italic">
                                근거 정책: {policyText.get(e.policyId)}
                              </p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>

                {/* 산출물 카드 */}
                <p className="eyebrow mt-8 mb-4">산출물</p>
                {detail.artifacts.length === 0 ? (
                  <div className="card bg-canvas-soft py-8 text-center text-sm text-mute">
                    이 밤엔 산출물이 없습니다.
                    {detail.tasks.some((t) => t.status === "skipped") &&
                      " (판단으로 건너뛴 작업이 있습니다 — 일지를 확인하세요.)"}
                  </div>
                ) : (
                  <div className="flex flex-col gap-4">
                    {detail.artifacts.map((a) => (
                      <article key={a.id} className="card">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <h3 className="display-sm">{a.title}</h3>
                            {a.task?.title && (
                              <p className="mt-1 text-xs text-mute">작업: {a.task.title}</p>
                            )}
                          </div>
                          <span
                            className={`shrink-0 font-mono text-[11px] tracking-wider uppercase ${
                              a.review === "approved"
                                ? "text-breeze"
                                : a.review === "rejected"
                                  ? "text-sunset"
                                  : "text-mute"
                            }`}
                          >
                            {REVIEW_LABEL[a.review] ?? a.review}
                          </span>
                        </div>

                        <pre className="mt-4 max-h-[28rem] overflow-auto rounded-[4px] bg-canvas-soft p-4 font-sans text-sm whitespace-pre-wrap text-body">
                          {a.content}
                        </pre>

                        {a.review === "pending" ? (
                          <ReviewActions artifactId={a.id} />
                        ) : (
                          <div className="mt-4 border-t border-hairline pt-4 text-sm text-mute">
                            {a.review === "approved" ? "승인 완료" : "반려 완료"}
                            {a.reviewReason && (
                              <p className="mt-1 text-sunset-soft">사유: {a.reviewReason}</p>
                            )}
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}

                {/* 이번 밤 작업 상태 */}
                {detail.tasks.length > 0 && (
                  <>
                    <p className="eyebrow mt-8 mb-3">이번 밤 작업</p>
                    <div className="flex flex-col gap-1">
                      {detail.tasks.map((t) => (
                        <div
                          key={t.id}
                          className="flex items-center justify-between border-b border-hairline py-2 text-sm"
                        >
                          <span className="text-body">{t.title}</span>
                          <span className="font-mono text-[11px] tracking-wider text-mute uppercase">
                            {TASK_STATUS_LABEL[t.status] ?? t.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
