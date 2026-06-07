import { useMemo, useState, type CSSProperties } from "react";
import { AspectCanvas } from "../../components/harness/AspectCanvas";
import { TactileButton } from "../../components/harness/TactileButton";
import { demoAgents } from "../../data/demoAgents";
import { applyReview, generateDebateReceipt, runDebate, updateReputation } from "../../domain/debateEngine";
import type { DebateClaim, DebateRoom, ReviewStatus } from "../../domain/opencanal";

type DebateRoomViewProps = {
  question: string;
  onReturn: () => void;
};

const reviewOptions: ReviewStatus[] = ["accepted", "disputed", "weak", "blocked", "needs_more_evidence", "out_of_mandate"];

function agentFor(agentId: string) {
  return demoAgents.find((agent) => agent.agent_id === agentId);
}

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
  const evidenceCount = Object.keys(run.receipt.evidence_snapshot).length;
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
        <div className="debate-abyss" aria-hidden="true" />
        <header className="debate-header">
          <TactileButton tone="quiet" onClick={onReturn}>
            Gateway
          </TactileButton>
          <div>
            <p>Agent Debate Room</p>
            <h1>{run.room.debate_question}</h1>
          </div>
          <span className="debate-receipt-id">{run.receipt.receipt_id}</span>
        </header>

        <section className="debate-field" aria-label="Agent debate field">
          <div className="debate-question-core">
            <span>Current Claim</span>
            <strong>{selectedClaim?.original_claim}</strong>
          </div>

          <div className="agent-ring-map" aria-label="Participating agents">
            {demoAgents.map((agent, index) => (
              <button
                className={`debate-agent-node debate-agent-node--${agent.role}`}
                key={agent.agent_id}
                style={{ "--agent-index": index } as CSSProperties}
                type="button"
                onClick={() => {
                  const claim = run.room.claims.find((item) => item.agent_id === agent.agent_id);
                  if (claim) setSelectedClaimId(claim.claim_id);
                }}
              >
                <span />
                <small>{agent.display_name}</small>
              </button>
            ))}
          </div>

          <div className="claim-orbits" aria-hidden="true">
            {run.room.claims.map((claim, index) => (
              <span className={`claim-orbit claim-orbit--${claim.stance}`} key={claim.claim_id} style={{ "--claim-index": index } as CSSProperties} />
            ))}
          </div>
        </section>

        <aside className="claim-stream" aria-label="Claim stream">
          <p>Claim / Evidence Stream</p>
          {run.room.claims.map((claim) => {
            const agent = agentFor(claim.agent_id);
            const active = claim.claim_id === selectedClaim?.claim_id;
            return (
              <button className={`claim-card ${active ? "is-active" : ""}`} key={claim.claim_id} type="button" onClick={() => setSelectedClaimId(claim.claim_id)}>
                <span>{agent?.display_name ?? claim.agent_id}</span>
                <strong>{claim.original_claim}</strong>
                <em>{statusLabel(claim.review_status)}</em>
              </button>
            );
          })}
        </aside>

        <aside className="evidence-constellation" aria-label="Evidence constellation">
          <p>Evidence</p>
          {Object.values(run.receipt.evidence_snapshot).map((source, index) => (
            <article key={source.source_id} style={{ "--evidence-index": index } as CSSProperties}>
              <span>{source.source_type}</span>
              <strong>{source.title}</strong>
            </article>
          ))}
        </aside>

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
          <p>Debate Receipt</p>
          <div className="receipt-panel__metrics">
            <span>{acceptedCount} accepted</span>
            <span>{disputedCount} disputed</span>
            <span>{blockedCount} blocked</span>
            <span>{evidenceCount} evidence</span>
          </div>
          <strong>{run.receipt.transcript_hash}</strong>
          <small>{run.receipt.moderator_summary}</small>
        </section>
      </AspectCanvas>
    </main>
  );
}
