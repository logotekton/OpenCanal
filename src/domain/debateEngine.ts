import { debateEvidence, demoAgents, demoMandates } from "../data/demoAgents";
import type {
  Agent,
  AgentRuntime,
  DebateClaim,
  DebateReceipt,
  DebateRoom,
  DebateRunResult,
  DebateStance,
  EvidenceSource,
  Mandate,
  MandateAction,
  ReputationGraph,
  ReviewEvent,
  ReviewStatus,
  RiskLevel
} from "./opencanal";

const fixedCreatedAt = "2026-06-07T00:00:00.000Z";

function idFrom(text: string) {
  return text.toLowerCase().replace(/[^a-z0-9가-힣]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 48);
}

function stableHash(value: unknown) {
  const text = JSON.stringify(value);
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function findMandate(room: DebateRoom, agent: Agent) {
  return room.mandates.find((mandate) => mandate.agent_id === agent.agent_id);
}

function hasAction(mandate: Mandate | undefined, action: MandateAction) {
  return Boolean(mandate?.allowed_actions.includes(action));
}

function uniqueEvidence(claims: DebateClaim[]) {
  const evidence = new Map<string, EvidenceSource>();
  for (const claim of claims) {
    for (const source of claim.evidence) {
      evidence.set(source.source_id, source);
    }
  }
  return Array.from(evidence.values());
}

function stanceMap(claims: DebateClaim[]): Record<DebateStance, string[]> {
  const initial: Record<DebateStance, string[]> = {
    support: [],
    oppose: [],
    refine: [],
    question: [],
    neutral: []
  };

  return claims.reduce((map, claim) => {
    map[claim.stance].push(claim.claim_id);
    return map;
  }, initial);
}

export function normalizeClaim(claim: DebateClaim, room: DebateRoom, agent: Agent): DebateClaim {
  const mandate = findMandate(room, agent);
  const inMandate = hasAction(mandate, "can_claim") && hasAction(mandate, "can_debate");
  const hasEvidence = claim.evidence.length > 0;
  const moderatorBacked = Boolean(claim.moderator_rationale);
  const blockedRisk = claim.risk_level === "high" || claim.risk_level === "blocked";

  if (!inMandate) {
    return {
      ...claim,
      mandate_check: "out_of_mandate",
      review_status: "out_of_mandate",
      is_hypothesis: !hasEvidence
    };
  }

  if (blockedRisk) {
    return {
      ...claim,
      mandate_check: "in_mandate",
      review_status: "blocked",
      is_hypothesis: !hasEvidence
    };
  }

  if (claim.review_status === "accepted" && !hasEvidence && !moderatorBacked) {
    return {
      ...claim,
      mandate_check: "in_mandate",
      review_status: "needs_more_evidence",
      is_hypothesis: true
    };
  }

  if (!hasEvidence && !moderatorBacked) {
    return {
      ...claim,
      mandate_check: "in_mandate",
      review_status: claim.review_status === "pending" ? "needs_more_evidence" : claim.review_status,
      is_hypothesis: true
    };
  }

  return {
    ...claim,
    mandate_check: "in_mandate",
    is_hypothesis: false
  };
}

function makeClaim(input: {
  room: DebateRoom;
  agent: Agent;
  stance: DebateStance;
  original: string;
  interpretation: string;
  application: string;
  evidence?: EvidenceSource[];
  counters?: string[];
  responsibility: string;
  risk?: RiskLevel;
  review?: ReviewStatus;
  rationale?: string;
}): DebateClaim {
  return {
    claim_id: `claim-${input.agent.role}-${idFrom(input.original)}`,
    room_id: input.room.room_id,
    agent_id: input.agent.agent_id,
    stance: input.stance,
    original_claim: input.original,
    interpretation_claim: input.interpretation,
    ai_application_claim: input.application,
    evidence: input.evidence ?? [],
    counterarguments: input.counters ?? [],
    responsibility: input.responsibility,
    mandate_check: "unclear",
    risk_level: input.risk ?? "low",
    review_status: input.review ?? "pending",
    is_hypothesis: false,
    moderator_rationale: input.rationale,
    created_at: fixedCreatedAt
  };
}

export class MockAgentRuntime implements AgentRuntime {
  runOpeningClaim(agent: Agent, room: DebateRoom): DebateClaim {
    if (agent.role === "opponent") {
      return normalizeClaim(
        makeClaim({
          room,
          agent,
          stance: "oppose",
          original: "Debate Room first is correct only if it proves reusable protocol objects, not just a pretty conversation UI.",
          interpretation: "The platform claim needs evidence, mandate checks, and receipts before applied commerce.",
          application: "The MVP must expose claim/evidence/counterclaim/review instead of hiding them behind chatbot copy.",
          evidence: [debateEvidence[1]],
          counters: ["A UI-only prototype would not prove the platform essence."],
          responsibility: "Challenge scope inflation and unsupported platform claims.",
          review: "disputed"
        }),
        room,
        agent
      );
    }

    return normalizeClaim(
      makeClaim({
        room,
        agent,
        stance: "support",
        original: "OpenCanal should begin with agent-to-agent Debate Room before BEBECIEN commerce.",
        interpretation: "The first proof should demonstrate verified agents exchanging structured claims and evidence.",
        application: "Commerce can later reuse the same interaction protocol without inventing a separate counsel flow.",
        evidence: [debateEvidence[0]],
        responsibility: "Argue the platform-first position using project plans.",
        review: "accepted"
      }),
      room,
      agent
    );
  }

  runCounterClaim(agent: Agent, room: DebateRoom, target: DebateClaim): DebateClaim {
    return normalizeClaim(
      makeClaim({
        room,
        agent,
        stance: "question",
        original: "The claim needs a concrete receipt path before it can count as platform proof.",
        interpretation: "A debate without final evidence package remains an interaction demo.",
        application: "The Room must generate Debate Receipt and update Reputation v0 in the same flow.",
        evidence: [debateEvidence[2]],
        counters: [target.original_claim],
        responsibility: "Force the debate toward verifiable outcome rather than abstract positioning.",
        review: "accepted"
      }),
      room,
      agent
    );
  }

  runEvidenceCheck(agent: Agent, room: DebateRoom): DebateClaim {
    return normalizeClaim(
      makeClaim({
        room,
        agent,
        stance: "refine",
        original: "The strongest supported claim is that Debate Room validates OpenCanal's reusable protocol objects.",
        interpretation: "The evidence supports Debate Room first, but not any claim of completed network infrastructure.",
        application: "The MVP should label unsupported future-network claims as hypotheses.",
        evidence: [debateEvidence[0], debateEvidence[2]],
        responsibility: "Separate evidence-backed claims from speculative roadmap language.",
        review: "accepted"
      }),
      room,
      agent
    );
  }

  runGovernanceReview(agent: Agent, room: DebateRoom): DebateClaim {
    return normalizeClaim(
      makeClaim({
        room,
        agent,
        stance: "neutral",
        original: "No agent should make commercial or safety recommendations in the Debate Room MVP.",
        interpretation: "BEBECIEN and product advice are explicitly Phase 2 applied vertical concerns.",
        application: "The Debate Room may discuss BEBECIEN as a scenario but must not produce product recommendations.",
        evidence: [debateEvidence[0]],
        responsibility: "Guard mandate boundaries and prevent vertical scope drift.",
        risk: "medium",
        review: "accepted"
      }),
      room,
      agent
    );
  }

  generateModeratorSummary(_agent: Agent, room: DebateRoom): string {
    const accepted = room.claims.filter((claim) => claim.review_status === "accepted").length;
    const disputed = room.claims.filter((claim) => claim.review_status === "disputed").length;
    return `Debate completed with ${accepted} accepted claim(s), ${disputed} disputed claim(s), and a receipt-ready protocol path. The outcome supports Debate Room as the Phase 1 proof while keeping commerce verticals out of v0 scope.`;
  }
}

export function createDebateRoom(question: string, agents = demoAgents, mandates = demoMandates): DebateRoom {
  return {
    room_id: `room-${stableHash(question).replace("fnv1a-", "")}`,
    title: "OpenCanal Agent Debate Room",
    debate_question: question,
    room_type: "debate",
    participants: agents.map((agent) => agent.agent_id),
    mandates,
    claims: [],
    evidence_table: [],
    stance_map: { support: [], oppose: [], refine: [], question: [], neutral: [] },
    review_events: [],
    status: "draft",
    created_at: fixedCreatedAt
  };
}

export function applyReview(room: DebateRoom, claimId: string, status: ReviewStatus, note: string): DebateRoom {
  const claim = room.claims.find((item) => item.claim_id === claimId);
  if (!claim) return room;

  const updatedClaims = room.claims.map((item) => (item.claim_id === claimId ? { ...item, review_status: status } : item));
  const event: ReviewEvent = {
    event_id: `review-${room.review_events.length + 1}`,
    claim_id: claimId,
    reviewer_agent_id: "agent-moderator",
    from_status: claim.review_status,
    to_status: status,
    note,
    created_at: fixedCreatedAt
  };

  return {
    ...room,
    claims: updatedClaims,
    evidence_table: uniqueEvidence(updatedClaims),
    stance_map: stanceMap(updatedClaims),
    review_events: [...room.review_events, event],
    status: "under_review"
  };
}

export function generateDebateReceipt(room: DebateRoom, agents = demoAgents, moderatorSummary = ""): DebateReceipt {
  const acceptedClaims = room.claims.filter(
    (claim) =>
      claim.review_status === "accepted" &&
      claim.risk_level !== "high" &&
      claim.risk_level !== "blocked" &&
      (claim.evidence.length > 0 || Boolean(claim.moderator_rationale))
  );
  const disputedClaims = room.claims.filter((claim) => claim.review_status === "disputed" || claim.review_status === "weak" || claim.review_status === "needs_more_evidence");
  const blockedClaims = room.claims.filter((claim) => claim.review_status === "blocked" || claim.review_status === "out_of_mandate");
  const evidenceSnapshot = Object.fromEntries(uniqueEvidence(room.claims).map((source) => [source.source_id, source]));

  return {
    receipt_id: `receipt-${room.room_id}`,
    room_id: room.room_id,
    debate_question: room.debate_question,
    participating_agents: room.participants,
    mandate_snapshot: Object.fromEntries(room.mandates.map((mandate) => [mandate.agent_id, mandate])),
    accepted_claims: acceptedClaims,
    disputed_claims: disputedClaims,
    blocked_claims: blockedClaims,
    evidence_snapshot: evidenceSnapshot,
    moderator_summary: moderatorSummary,
    transcript_hash: stableHash(room.claims.map((claim) => [claim.agent_id, claim.original_claim, claim.review_status])),
    agent_versions: Object.fromEntries(agents.map((agent) => [agent.agent_id, agent.version])),
    status: "approved",
    created_at: fixedCreatedAt
  };
}

export function updateReputation(room: DebateRoom, receipt: DebateReceipt, agents = demoAgents): ReputationGraph[] {
  return agents.map((agent) => {
    const claims = room.claims.filter((claim) => claim.agent_id === agent.agent_id);
    const evidenced = claims.filter((claim) => claim.evidence.length > 0 || Boolean(claim.moderator_rationale)).length;
    const blocked = claims.filter((claim) => claim.review_status === "blocked" || claim.review_status === "out_of_mandate").length;
    const disputed = claims.filter((claim) => receipt.disputed_claims.some((item) => item.claim_id === claim.claim_id)).length;

    return {
      reputation_id: agent.reputation_id,
      agent_id: agent.agent_id,
      response_count: claims.length,
      receipt_count: room.participants.includes(agent.agent_id) ? 1 : 0,
      evidence_coverage_rate: claims.length === 0 ? 0 : evidenced / claims.length,
      human_revision_rate: room.review_events.filter((event) => claims.some((claim) => claim.claim_id === event.claim_id)).length / Math.max(claims.length, 1),
      blocked_response_count: blocked,
      dispute_count: disputed,
      last_updated: fixedCreatedAt
    };
  });
}

export function runDebate(question: string, runtime: AgentRuntime = new MockAgentRuntime(), agents = demoAgents, mandates = demoMandates): DebateRunResult {
  const room = createDebateRoom(question, agents, mandates);
  room.status = "active";

  const proponent = agents.find((agent) => agent.role === "proponent")!;
  const opponent = agents.find((agent) => agent.role === "opponent")!;
  const evidenceAgent = agents.find((agent) => agent.role === "evidence")!;
  const governanceAgent = agents.find((agent) => agent.role === "governance")!;
  const moderator = agents.find((agent) => agent.role === "moderator")!;

  const opening = runtime.runOpeningClaim(proponent, room);
  const opposing = runtime.runOpeningClaim(opponent, { ...room, claims: [opening] });
  const counter = runtime.runCounterClaim(opponent, { ...room, claims: [opening, opposing] }, opening);
  const evidenceCheck = runtime.runEvidenceCheck(evidenceAgent, { ...room, claims: [opening, opposing, counter] });
  const governance = runtime.runGovernanceReview(governanceAgent, { ...room, claims: [opening, opposing, counter, evidenceCheck] });

  const claims = [opening, opposing, counter, evidenceCheck, governance];
  const reviewedRoom: DebateRoom = {
    ...room,
    claims,
    evidence_table: uniqueEvidence(claims),
    stance_map: stanceMap(claims),
    status: "receipt_ready"
  };

  const moderatorSummary = runtime.generateModeratorSummary(moderator, reviewedRoom);
  const receipt = generateDebateReceipt(reviewedRoom, agents, moderatorSummary);

  return {
    room: {
      ...reviewedRoom,
      debate_receipt_id: receipt.receipt_id,
      status: "closed"
    },
    receipt,
    reputation: updateReputation(reviewedRoom, receipt, agents)
  };
}
