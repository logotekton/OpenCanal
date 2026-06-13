import { notFound, redirect } from "next/navigation";
import { prisma } from "@opencanal/db";
import { requireUser } from "@/lib/session";
import { VerifiedBadge } from "@/components/badge";

export const dynamic = "force-dynamic";

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

  return (
    <main className="px-6 py-12">
      <div className="mx-auto max-w-2xl">
        <p className="eyebrow mb-2">CONTRACT RECEIPT</p>
        <h1 className="display-md">거래 확정 영수증</h1>

        <div className="card mt-8 border-sunset">
          <p className="eyebrow mb-4">AGREED TERMS</p>
          <p className="text-body whitespace-pre-wrap">{receipt.terms}</p>
        </div>

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

        <p className="mt-6 text-xs text-mute">
          이 영수증은 확정 시점까지의 대화 기록 해시를 포함하는 불변 기록입니다. OpenCanal은 결제를
          처리하지 않으며, 이 기록은 양 당사자 간 합의의 증거로 기능합니다.
        </p>
      </div>
    </main>
  );
}
