import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { PairingPanel } from "./pairing-panel";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function RunnerSettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ agent?: string }>;
}) {
  const user = await requireUser();
  const { agent: preselect } = await searchParams;

  const agents = await prisma.agent.findMany({
    where: { ownerId: user.id },
    include: { device: { select: { id: true, name: true, lastSeenAt: true, runnerVersion: true } } },
    orderBy: { createdAt: "desc" },
  });

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-3xl">
        <p className="eyebrow mb-2">RUNNER</p>
        <h1 className="display-md">로컬 러너 연결</h1>
        <p className="mt-4 max-w-xl text-body">
          러너는 당신의 머신에서 agent의 두뇌(Claude/GPT 구독)를 돌리는 백그라운드
          프로세스입니다. LLM 자격증명과 OpenCrab 토큰은 당신의 머신을 떠나지 않습니다.
        </p>

        {agents.length === 0 ? (
          <div className="card mt-8 bg-canvas-soft py-10 text-center">
            <p className="text-mute">먼저 agent를 만들어주세요.</p>
            <Link href="/agents/new" className="pill pill-primary mt-4 inline-flex">
              agent 만들기
            </Link>
          </div>
        ) : (
          <div className="mt-8 flex flex-col gap-6">
            {agents.map((a) => (
              <PairingPanel
                key={a.id}
                agent={{
                  id: a.id,
                  handle: a.handle,
                  displayName: a.displayName,
                  status: a.status,
                  device: a.device
                    ? {
                        name: a.device.name,
                        lastSeenAt: a.device.lastSeenAt?.toISOString() ?? null,
                        runnerVersion: a.device.runnerVersion,
                      }
                    : null,
                }}
                defaultOpen={a.id === preselect}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
