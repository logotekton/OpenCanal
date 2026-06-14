import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@opencanal/db";
import { getSessionUser } from "@/lib/session";
import { getAgentReputation } from "@/lib/reputation";
import { VerifiedBadge, LevelChip } from "@/components/badge";
import { PresenceDot } from "@/components/presence";
import { AskAgentButton } from "./ask-button";
import { RequestVerificationForm } from "./request-verification";
import { PermissionsPanel } from "./permissions-panel";
import { CapabilityEditor } from "./capability-editor";

export const dynamic = "force-dynamic";

function pctText(v: number | null): string {
  return v !== null ? `${v}%` : "—";
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="card py-4 text-center">
      <p className={`display-md ${tone === "warn" ? "text-sunset" : ""}`}>{value}</p>
      <p className="mt-1 text-xs text-mute">{label}</p>
    </div>
  );
}

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
      capabilities: {
        where: { enabled: true },
        orderBy: { createdAt: "asc" },
        select: { key: true, label: true, description: true, requiresApproval: true },
      },
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

  // 평판 v1 — 자기소개가 아니라 실행 결과로 계산한다 (응답률·승인률·이행률·분쟁률·근거점수 + 합성 신뢰점수)
  const reputation = await getAgentReputation(agent.id);

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
          <div className="card flex items-baseline justify-between bg-canvas-soft">
            <div>
              <p className="display-md">
                {reputation.trustScore !== null ? reputation.trustScore : "—"}
                <span className="text-base text-mute"> / 100</span>
              </p>
              <p className="mt-1 text-xs text-mute">신뢰 점수 — 실행 결과 기반</p>
            </div>
            <p className="text-xs text-mute">
              표본 {reputation.sampleSize} · 확정 거래 {reputation.transactionCount}건
            </p>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Metric label="응답률" value={pctText(reputation.responseRate)} />
            <Metric label="소유자 승인률" value={pctText(reputation.approvalRate)} />
            <Metric label="이행률" value={pctText(reputation.fulfillmentRate)} />
            <Metric
              label="분쟁률"
              value={pctText(reputation.disputeRate)}
              tone={reputation.disputeRate && reputation.disputeRate > 0 ? "warn" : undefined}
            />
            <Metric label="근거점수" value={pctText(reputation.evidenceScore)} />
            <Metric label="보낸 메시지" value={String(reputation.messagesSent)} />
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

        {agent.capabilities.length > 0 && (
          <section className="mt-10">
            <p className="eyebrow mb-3">CAPABILITIES</p>
            <div className="flex flex-col gap-2">
              {agent.capabilities.map((c) => (
                <div
                  key={c.key}
                  className="card flex items-center justify-between gap-3 py-3 bg-canvas-soft"
                >
                  <div>
                    <p className="text-sm text-body">{c.label}</p>
                    {c.description && <p className="mt-0.5 text-xs text-mute">{c.description}</p>}
                  </div>
                  {c.requiresApproval && (
                    <span className="shrink-0 rounded-full border border-hairline px-2.5 py-0.5 text-xs text-mute">
                      승인 필요
                    </span>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-mute">
              모든 능력은 소유자 승인 봉투 안에서만 수행됩니다.
            </p>
          </section>
        )}

        {isOwner && (
          <>
            <section className="mt-10">
              <p className="eyebrow mb-3">PERMISSIONS</p>
              <PermissionsPanel agentId={agent.id} canNegotiate={!!permissions.can_negotiate} />
            </section>

            <section className="mt-10">
              <p className="eyebrow mb-3">CAPABILITIES 관리</p>
              <CapabilityEditor agentId={agent.id} />
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
