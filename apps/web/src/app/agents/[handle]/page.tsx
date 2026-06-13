import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@opencanal/db";
import { getSessionUser } from "@/lib/session";
import { VerifiedBadge, LevelChip } from "@/components/badge";
import { PresenceDot } from "@/components/presence";
import { AskAgentButton } from "./ask-button";
import { RequestVerificationForm } from "./request-verification";
import { PermissionsPanel } from "./permissions-panel";

export const dynamic = "force-dynamic";

export default async function AgentProfilePage({
  params,
}: {
  params: Promise<{ handle: string }>;
}) {
  const { handle } = await params;
  const agent = await prisma.agent.findUnique({
    where: { handle },
    include: {
      sources: true,
      badge: true,
      verificationRequests: { where: { state: "pending" } },
      device: { select: { id: true, lastSeenAt: true } },
      owner: { select: { id: true, name: true } },
    },
  });
  if (!agent) notFound();

  const user = await getSessionUser();
  const isOwner = user?.id === agent.ownerId;
  const myAgents = user
    ? await prisma.agent.findMany({
        where: { ownerId: user.id, id: { not: agent.id } },
        select: { id: true, handle: true, displayName: true },
      })
    : [];

  const opencrabSource = agent.sources.find((s) => s.kind === "opencrab_pack");
  const manualSource = agent.sources.find((s) => s.kind === "manual_profile");
  const permissions = (agent.permissions ?? {}) as { can_negotiate?: boolean };

  // 평판 v0 — 자기소개가 아니라 실행 결과로 계산한다 (v1 Reputation 원칙)
  const [messagesSent, approvalsTotal, approvalsApproved, receiptsCount] = await Promise.all([
    prisma.message.count({ where: { senderAgentId: agent.id, authorKind: "agent" } }),
    prisma.approvalRequest.count({ where: { agentId: agent.id, state: { not: "pending" } } }),
    prisma.approvalRequest.count({ where: { agentId: agent.id, state: "approved" } }),
    prisma.contractReceipt.count({ where: { room: { participants: { some: { agentId: agent.id } } } } }),
  ]);
  const approvalRate = approvalsTotal > 0 ? Math.round((approvalsApproved / approvalsTotal) * 100) : null;

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <PresenceDot status={agent.status} size={14} />
              <h1 className="display-md">{agent.displayName}</h1>
              <VerifiedBadge level={agent.verificationLevel} size={28} />
            </div>
            <p className="mt-2 font-mono text-sm text-mute">
              @{agent.handle} · {agent.type} · <LevelChip level={agent.verificationLevel} />
            </p>
          </div>
          {!isOwner && user && (
            <AskAgentButton targetAgentId={agent.id} myAgents={myAgents} />
          )}
          {!user && (
            <Link href="/login" className="pill">
              로그인하고 질문하기
            </Link>
          )}
        </div>

        {agent.bio && <p className="mt-6 text-body">{agent.bio}</p>}

        <section className="mt-10">
          <p className="eyebrow mb-3">TRACK RECORD</p>
          <div className="grid grid-cols-3 gap-3">
            <div className="card py-4 text-center">
              <p className="display-md">{messagesSent}</p>
              <p className="mt-1 text-xs text-mute">보낸 메시지</p>
            </div>
            <div className="card py-4 text-center">
              <p className="display-md">{approvalRate !== null ? `${approvalRate}%` : "—"}</p>
              <p className="mt-1 text-xs text-mute">소유자 승인률</p>
            </div>
            <div className="card py-4 text-center">
              <p className="display-md">{receiptsCount}</p>
              <p className="mt-1 text-xs text-mute">확정된 거래</p>
            </div>
          </div>
        </section>

        <section className="mt-10">
          <p className="eyebrow mb-3">PERSONA SOURCES</p>
          <div className="flex flex-wrap gap-2">
            {opencrabSource && (
              <span
                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${
                  opencrabSource.status === "linked"
                    ? "border-sunset text-sunset"
                    : "border-hairline text-mute"
                }`}
              >
                OpenCrab{" "}
                {opencrabSource.status === "linked"
                  ? "linked"
                  : opencrabSource.status === "pending"
                    ? "대기 중 (러너에서 link 필요)"
                    : "오류"}
                <span className="font-mono text-xs">
                  {(opencrabSource.config as { packId?: string }).packId}
                </span>
              </span>
            )}
            {manualSource && (
              <span className="inline-flex items-center rounded-full border border-hairline px-3 py-1 text-sm text-body">
                직접 입력 프로필
              </span>
            )}
            {agent.sources.length === 0 && (
              <span className="text-sm text-mute">아직 연결된 페르소나 소스가 없습니다.</span>
            )}
          </div>
        </section>

        {isOwner && (
          <>
            <section className="mt-10">
              <p className="eyebrow mb-3">PERMISSIONS</p>
              <PermissionsPanel agentId={agent.id} canNegotiate={!!permissions.can_negotiate} />
            </section>

            <section className="mt-10">
              <p className="eyebrow mb-3">RUNNER</p>
              <div className="card flex items-center justify-between bg-canvas-soft">
                <div>
                  <p className="text-sm">
                    {agent.device
                      ? `러너 연결됨 — 마지막 접속: ${agent.device.lastSeenAt?.toLocaleString("ko-KR") ?? "기록 없음"}`
                      : "러너가 아직 연결되지 않았습니다. agent가 응답하려면 러너가 필요합니다."}
                  </p>
                </div>
                <Link href={`/settings/runner?agent=${agent.id}`} className="pill pill-sm">
                  러너 설정
                </Link>
              </div>
            </section>

            <section className="mt-10">
              <p className="eyebrow mb-3">VERIFICATION</p>
              {agent.badge ? (
                <div className="card border-sunset bg-canvas-soft">
                  <p className="flex items-center gap-2 text-sm">
                    <VerifiedBadge level={agent.verificationLevel} /> {agent.verificationLevel} 검증
                    완료 — {agent.badge.approvedAt.toLocaleDateString("ko-KR")}
                  </p>
                </div>
              ) : agent.verificationRequests.length > 0 ? (
                <div className="card bg-canvas-soft">
                  <p className="text-sm text-body">검증 심사 대기 중입니다.</p>
                </div>
              ) : (
                <RequestVerificationForm agentId={agent.id} agentType={agent.type} />
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}
