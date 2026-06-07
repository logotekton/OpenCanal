import { describe, expect, it } from "vitest";
import { demoAgents, demoMandates } from "../data/demoAgents";
import { createDebateRoom, generateDebateReceipt, normalizeClaim, runDebate, updateReputation } from "../domain/debateEngine";
import type { DebateClaim, EvidenceSource, Mandate } from "../domain/opencanal";

const evidence: EvidenceSource = {
  source_id: "test-evidence",
  title: "Test evidence",
  source_type: "scenario",
  excerpt: "A test source supporting the claim.",
  confidence: 0.9
};

function claim(overrides: Partial<DebateClaim> = {}): DebateClaim {
  return {
    claim_id: "claim-test",
    room_id: "room-test",
    agent_id: demoAgents[0].agent_id,
    stance: "support",
    original_claim: "Test original claim",
    interpretation_claim: "Test interpretation",
    ai_application_claim: "Test application",
    evidence: [evidence],
    counterarguments: [],
    responsibility: "Test responsibility",
    mandate_check: "unclear",
    risk_level: "low",
    review_status: "accepted",
    is_hypothesis: false,
    created_at: "2026-06-07T00:00:00.000Z",
    ...overrides
  };
}

describe("debate engine", () => {
  it("runs a debate with at least four agents and creates a receipt", () => {
    const result = runDebate("OpenCanal should start with agent debate first.");

    expect(result.room.participants.length).toBeGreaterThanOrEqual(4);
    expect(result.room.claims.length).toBeGreaterThanOrEqual(4);
    expect(result.receipt.room_id).toBe(result.room.room_id);
    expect(result.receipt.debate_question).toBe(result.room.debate_question);
    expect(result.receipt.participating_agents.length).toBe(result.room.participants.length);
    expect(Object.keys(result.receipt.evidence_snapshot).length).toBeGreaterThan(0);
    expect(result.receipt.transcript_hash).toMatch(/^fnv1a-/);
  });

  it("allows evidence-backed accepted claims into the receipt", () => {
    const room = createDebateRoom("Evidence-backed claims should pass.");
    const accepted = claim({ room_id: room.room_id, evidence: [evidence], review_status: "accepted" });
    const receipt = generateDebateReceipt({ ...room, claims: [accepted] });

    expect(receipt.accepted_claims).toHaveLength(1);
    expect(receipt.accepted_claims[0].claim_id).toBe(accepted.claim_id);
  });

  it("downgrades unsupported accepted claims to needs_more_evidence and hypothesis", () => {
    const room = createDebateRoom("Unsupported claims should not be accepted.");
    const unsupported = claim({ room_id: room.room_id, evidence: [], review_status: "accepted" });

    const normalized = normalizeClaim(unsupported, room, demoAgents[0]);

    expect(normalized.review_status).toBe("needs_more_evidence");
    expect(normalized.is_hypothesis).toBe(true);
  });

  it("flags claims outside the mandate", () => {
    const room = createDebateRoom("Out of mandate claims should be flagged.");
    const restrictedMandate: Mandate = {
      ...demoMandates[0],
      allowed_actions: ["can_answer"]
    };
    const restrictedRoom = {
      ...room,
      mandates: [restrictedMandate, ...demoMandates.slice(1)]
    };

    const normalized = normalizeClaim(claim({ room_id: room.room_id }), restrictedRoom, demoAgents[0]);

    expect(normalized.review_status).toBe("out_of_mandate");
    expect(normalized.mandate_check).toBe("out_of_mandate");
  });

  it("keeps blocked risk claims out of accepted receipt claims", () => {
    const room = createDebateRoom("Blocked risk should not become accepted.");
    const risky = claim({ room_id: room.room_id, risk_level: "blocked", review_status: "accepted" });
    const normalized = normalizeClaim(risky, room, demoAgents[0]);
    const receipt = generateDebateReceipt({ ...room, claims: [normalized] });

    expect(normalized.review_status).toBe("blocked");
    expect(receipt.accepted_claims).toHaveLength(0);
    expect(receipt.blocked_claims).toHaveLength(1);
  });

  it("updates reputation from receipt outcomes", () => {
    const room = createDebateRoom("Reputation should update.");
    const accepted = claim({ room_id: room.room_id, evidence: [evidence], review_status: "accepted" });
    const disputed = claim({
      claim_id: "claim-disputed",
      room_id: room.room_id,
      evidence: [],
      review_status: "needs_more_evidence"
    });
    const withClaims = { ...room, claims: [accepted, disputed] };
    const receipt = generateDebateReceipt(withClaims);

    const reputation = updateReputation(withClaims, receipt);
    const proponentReputation = reputation.find((item) => item.agent_id === demoAgents[0].agent_id);

    expect(proponentReputation?.response_count).toBe(2);
    expect(proponentReputation?.receipt_count).toBe(1);
    expect(proponentReputation?.evidence_coverage_rate).toBe(0.5);
    expect(proponentReputation?.dispute_count).toBe(1);
  });
});
