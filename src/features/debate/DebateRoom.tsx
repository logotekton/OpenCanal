import { useMemo, useState } from "react";
import { AspectCanvas } from "../../components/harness/AspectCanvas";
import { TactileButton } from "../../components/harness/TactileButton";
import { applyReview, generateDebateReceipt, runDebate, updateReputation } from "../../domain/debateEngine";
import type { DebateClaim, DebateRoom, ReviewStatus } from "../../domain/opencanal";
import { demoAgents } from "../../data/demoAgents";
import { SynapticField } from "./SynapticField";

type DebateRoomViewProps = {
  question: string;
  onReturn: () => void;
};

const reviewOptions: ReviewStatus[] = ["accepted", "disputed", "weak", "blocked", "needs_more_evidence", "out_of_mandate"];

function statusLabel(status: ReviewStatus) {
  return status.replaceAll("_", " ");
}

function applyModeratorReview(room: DebateRoom, claim: DebateClaim, status: ReviewStatus) {
  const reviewed = applyReview(room, claim.claim_id, status, `Human moderator marked ${claim.claim_id} as ${status}.`);
  const receipt = generateDebateReceipt(reviewed, demoAgents, "Human moderator updated the debate state and regenerated the receipt.");
  return {
    room: {
      ...reviewed,
      debate_receipt_id: receipt.receipt_id,
      status: "closed" as const
    },
    receipt,
    reputation: updateReputation(reviewed, receipt, demoAgents)
  };
}

export function DebateRoomView({ question, onReturn }: DebateRoomViewProps) {
  const initialRun = useMemo(() => runDebate(question), [question]);
  const [run, setRun] = useState(initialRun);
  const [selectedClaimId, setSelectedClaimId] = useState(initialRun.room.claims[0]?.claim_id ?? "");

  const selectedClaim = run.room.claims.find((claim) => claim.claim_id === selectedClaimId) ?? run.room.claims[0];
  const acceptedCount = run.receipt.accepted_claims.length;
  const disputedCount = run.receipt.disputed_claims.length;
  const blockedCount = run.receipt.blocked_claims.length;

  function reviewSelected(status: ReviewStatus) {
    if (!selectedClaim) return;
    const nextRun = applyModeratorReview(run.room, selectedClaim, status);
    setRun(nextRun);
  }

  return (
    <main className="debate-shell" aria-label="OpenCanal Debate Room">
      <AspectCanvas className="debate-canvas">
        <SynapticField claims={run.room.claims} selectedClaimId={selectedClaim?.claim_id ?? ""} onSelectClaim={setSelectedClaimId} />
        <header className="debate-header">
          <TactileButton tone="quiet" onClick={onReturn}>
            Gateway
          </TactileButton>
          <div>
            <p>Agent Debate Room</p>
            <h1>OpenCanal Debate</h1>
          </div>
          <span className="debate-receipt-id">{run.receipt.receipt_id}</span>
        </header>

        <section className="signal-inspector" aria-label="Selected signal">
          <p>Selected Signal</p>
          <strong>{selectedClaim?.original_claim}</strong>
          <span>{selectedClaim ? `${statusLabel(selectedClaim.review_status)} · ${selectedClaim.evidence.length} evidence source(s)` : "No active signal"}</span>
        </section>

        <section className="moderator-dock" aria-label="Moderator controls">
          <div>
            <p>Moderator</p>
            <strong>{selectedClaim ? statusLabel(selectedClaim.review_status) : "No claim"}</strong>
          </div>
          <div className="moderator-dock__actions">
            {reviewOptions.map((status) => (
              <TactileButton key={status} tone="quiet" onClick={() => reviewSelected(status)}>
                {statusLabel(status)}
              </TactileButton>
            ))}
          </div>
        </section>

        <section className="receipt-panel" aria-label="Debate Receipt">
          <p>Memory Trace</p>
          <div className="receipt-panel__metrics">
            <span>{acceptedCount} accepted</span>
            <span>{disputedCount} disputed</span>
            <span>{blockedCount} blocked</span>
            <span>{Object.keys(run.receipt.evidence_snapshot).length} evidence</span>
          </div>
          <strong>{run.receipt.transcript_hash}</strong>
        </section>
      </AspectCanvas>
    </main>
  );
}
