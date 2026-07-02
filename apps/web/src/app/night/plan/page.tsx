import Link from "next/link";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { DirectiveEditor, PolicyEditor, TaskEditor } from "./plan-editors";

export const dynamic = "force-dynamic";

export default async function NightPlanPage({
  searchParams,
}: {
  searchParams: Promise<{ agent?: string }>;
}) {
  const user = await requireUser();
  const sp = await searchParams;

  const agents = await prisma.agent.findMany({
    where: { ownerId: user.id },
    orderBy: { createdAt: "asc" },
    select: { id: true, displayName: true },
  });

  if (agents.length === 0) {
    return (
      <main className="px-6 py-12">
        <div className="mx-auto max-w-2xl">
          <p className="eyebrow mb-2">NIGHT · 계획</p>
          <h1 className="display-md">밤 계획</h1>
          <div className="card mt-8 bg-canvas-soft py-12 text-center text-mute">
            먼저 <Link href="/agents/new" className="text-sunset">agent를 만들어야</Link> 밤 계획을 세울 수 있습니다.
          </div>
        </div>
      </main>
    );
  }

  const selectedAgent = agents.find((a) => a.id === sp.agent) ?? agents[0];

  const [policies, directives, tasks] = await Promise.all([
    prisma.nightPolicy.findMany({
      where: { agentId: selectedAgent.id },
      orderBy: [{ kind: "asc" }, { createdAt: "asc" }],
      select: { id: true, kind: true, text: true, active: true },
    }),
    prisma.nightDirective.findMany({
      where: { agentId: selectedAgent.id },
      orderBy: { createdAt: "asc" },
      select: { id: true, content: true, active: true },
    }),
    prisma.nightTask.findMany({
      where: { agentId: selectedAgent.id },
      orderBy: [{ status: "asc" }, { order: "asc" }],
      select: { id: true, title: true, brief: true, originNote: true, status: true },
    }),
  ]);

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-3xl">
        <p className="eyebrow mb-2">NIGHT · 계획</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h1 className="display-md">밤 계획</h1>
          <Link href={`/night?agent=${selectedAgent.id}`} className="pill pill-sm">
            아침 리뷰로
          </Link>
        </div>
        <p className="mt-2 max-w-xl text-sm text-mute">
          agent가 밤에 무엇을 할 가치가 있는지 판단하는 근거입니다. 정책과 지시가 constitution에 주입되고, 모든 판단은 여기 정책을 출처로 인용합니다.
        </p>

        {agents.length > 1 && (
          <div className="mt-6 flex flex-wrap gap-2">
            {agents.map((a) => (
              <Link
                key={a.id}
                href={`/night/plan?agent=${a.id}`}
                className={`pill pill-sm ${a.id === selectedAgent.id ? "pill-primary" : ""}`}
              >
                {a.displayName}
              </Link>
            ))}
          </div>
        )}

        <section className="mt-10">
          <p className="eyebrow mb-4">판단 정책</p>
          <PolicyEditor agentId={selectedAgent.id} policies={policies} />
        </section>

        <section className="mt-10">
          <p className="eyebrow mb-4">상시 지시</p>
          <DirectiveEditor agentId={selectedAgent.id} directives={directives} />
        </section>

        <section className="mt-10">
          <p className="eyebrow mb-4">작업 카드 백로그</p>
          <TaskEditor agentId={selectedAgent.id} tasks={tasks} />
        </section>
      </div>
    </main>
  );
}
