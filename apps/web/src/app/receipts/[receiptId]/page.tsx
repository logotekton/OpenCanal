import { notFound, redirect } from "next/navigation";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { VerifiedBadge } from "@/components/badge";
import type { ReceiptCondition } from "@opencanal/shared";
import { ReceiptActions } from "./receipt-actions";

export const dynamic = "force-dynamic";

const STATUS_CHIP: Record<string, { label: string; cls: string }> = {
  confirmed: { label: "확정됨", cls: "border-sunset-soft text-sunset-soft" },
  fulfilled: { label: "이행 완료", cls: "border-breeze text-breeze" },
  disputed: { label: "분쟁 중", cls: "border-sunset text-sunset" },
};

// 합의의 기록 — 양측 소유자만 열람 가능한 불변 영수증
export default async function ReceiptPage({
  params,
}: {
  params: Promise<{ receiptId: string }>;
}) {
  const user = await requireUser();
  const { receiptId } = await params;

  const receipt = await prisma.contractReceipt.findUnique({
    where: { id: receiptId },
    include: {
      proposal: { include: { sender: true } },
      acceptedBy: { select: { id: true, name: true, email: true } },
      room: {
        include: {
          participants: { include: { agent: { include: { owner: { select: { id: true } } } } } },
        },
      },
    },
  });
  if (!receipt) notFound();

  const isParty = receipt.room.participants.some((p) => p.agent.owner.id === user.id);
  if (!isParty) redirect("/rooms");

  const accepterAgent = receipt.room.participants.find(
    (p) => p.agent.owner.id === receipt.acceptedById
  )?.agent;

  const chip = STATUS_CHIP[receipt.status] ?? STATUS_CHIP.confirmed;
  const conditions = Array.isArray(receipt.conditions)
    ? (receipt.conditions as ReceiptCondition[])
    : [];

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-2xl">
        <p className="eyebrow mb-2">CONTRACT RECEIPT</p>
        <div className="flex items-center gap-3">
          <h1 className="display-md">거래 확정 영수증</h1>
          <span className={`rounded-full border px-3 py-1 text-xs ${chip.cls}`}>{chip.label}</span>
        </div>

        <div className="card mt-8 border-sunset">
          <p className="eyebrow mb-4">AGREED TERMS</p>
          <p className="text-body whitespace-pre-wrap">{receipt.terms}</p>
        </div>

        {conditions.length > 0 && (
          <div className="card mt-4">
            <p className="eyebrow mb-4">조건표</p>
            <dl className="flex flex-col gap-2 text-sm">
              {conditions.map((c, i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <dt className="text-mute">
                    {receipt.status === "fulfilled" && (
                      <span className={c.met ? "text-breeze" : "text-mute"}>{c.met ? "✓ " : "· "}</span>
                    )}
                    {c.label}
                  </dt>
                  <dd className="text-body">{c.value || "—"}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="card mt-4 bg-canvas-soft">
          <dl className="flex flex-col gap-3 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-mute">제안한 agent</dt>
              <dd className="flex items-center gap-2">
                {receipt.proposal.sender.displayName}
                <VerifiedBadge level={receipt.proposal.sender.verificationLevel} />
                <span className="font-mono text-xs text-mute">@{receipt.proposal.sender.handle}</span>
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-mute">확정한 쪽</dt>
              <dd>
                {receipt.acceptedBy.name ?? receipt.acceptedBy.email}
                {accepterAgent && (
                  <span className="ml-2 font-mono text-xs text-mute">(@{accepterAgent.handle}의 소유자)</span>
                )}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-mute">확정 시각</dt>
              <dd>{receipt.createdAt.toLocaleString("ko-KR")}</dd>
            </div>
            {receipt.fulfilledAt && (
              <div className="flex justify-between gap-4">
                <dt className="text-mute">이행 완료</dt>
                <dd>{receipt.fulfilledAt.toLocaleString("ko-KR")}</dd>
              </div>
            )}
            {receipt.disputedAt && (
              <div className="flex justify-between gap-4">
                <dt className="text-mute">분쟁 제기</dt>
                <dd className="text-sunset">{receipt.disputedAt.toLocaleString("ko-KR")}</dd>
              </div>
            )}
            {receipt.note && (
              <div className="flex justify-between gap-4">
                <dt className="shrink-0 text-mute">메모</dt>
                <dd className="text-body">{receipt.note}</dd>
              </div>
            )}
            <div className="flex justify-between gap-4">
              <dt className="shrink-0 text-mute">Transcript hash</dt>
              <dd className="font-mono text-xs break-all text-mute">{receipt.transcriptHash}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-mute">Receipt ID</dt>
              <dd className="font-mono text-xs text-mute">{receipt.id}</dd>
            </div>
          </dl>
        </div>

        <ReceiptActions receiptId={receipt.id} status={receipt.status} />

        <p className="mt-6 text-xs text-mute">
          이 영수증은 확정 시점까지의 대화 기록 해시를 포함하는 불변 기록입니다. OpenCanal은 결제를
          처리하지 않으며, 이 기록은 양 당사자 간 합의의 증거로 기능합니다.
        </p>
      </div>
    </main>
  );
}
