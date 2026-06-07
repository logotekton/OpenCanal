import type { Agent, EvidenceSource, Mandate } from "../domain/opencanal";

export const demoAgents: Agent[] = [
  {
    agent_id: "agent-proponent",
    agent_type: "enterprise",
    display_name: "Proponent Agent",
    role: "proponent",
    owner_id: "opencanal",
    verification_status: "verified",
    verification_level: "L0_simulation",
    version: "0.1.0",
    reputation_id: "rep-proponent"
  },
  {
    agent_id: "agent-opponent",
    agent_type: "enterprise",
    display_name: "Opponent Agent",
    role: "opponent",
    owner_id: "opencanal",
    verification_status: "verified",
    verification_level: "L0_simulation",
    version: "0.1.0",
    reputation_id: "rep-opponent"
  },
  {
    agent_id: "agent-evidence",
    agent_type: "enterprise",
    display_name: "Evidence Agent",
    role: "evidence",
    owner_id: "opencanal",
    verification_status: "verified",
    verification_level: "L0_simulation",
    version: "0.1.0",
    reputation_id: "rep-evidence"
  },
  {
    agent_id: "agent-governance",
    agent_type: "admin",
    display_name: "Governance Agent",
    role: "governance",
    owner_id: "opencanal",
    verification_status: "verified",
    verification_level: "L0_simulation",
    version: "0.1.0",
    reputation_id: "rep-governance"
  },
  {
    agent_id: "agent-moderator",
    agent_type: "admin",
    display_name: "Moderator Agent",
    role: "moderator",
    owner_id: "opencanal",
    verification_status: "verified",
    verification_level: "L0_simulation",
    version: "0.1.0",
    reputation_id: "rep-moderator"
  }
];

export const demoMandates: Mandate[] = demoAgents.map((agent) => ({
  mandate_id: `mandate-${agent.agent_id}`,
  agent_id: agent.agent_id,
  allowed_actions:
    agent.role === "moderator"
      ? ["can_claim", "can_debate", "can_generate_receipt"]
      : ["can_claim", "can_debate", "can_counterargue"],
  scope: "OpenCanal Phase 1 agent debate protocol",
  human_approval_required: agent.role === "governance"
}));

export const debateEvidence: EvidenceSource[] = [
  {
    source_id: "evidence-master-plan-phase-1",
    title: "OpenCanal Platform Master Plan v1.1",
    source_type: "prd",
    excerpt: "The first proof is an agent-to-agent Debate Room where verified agents exchange claims, evidence, counterarguments, approvals, and receipts.",
    confidence: 0.96
  },
  {
    source_id: "evidence-debate-prd-required-roles",
    title: "Agent Debate Room PRD v0.1",
    source_type: "prd",
    excerpt: "Minimum v0.1 roles include Proponent, Opponent, Evidence, Safety/Governance, and Moderator.",
    confidence: 0.94
  },
  {
    source_id: "evidence-core-ontology-rules",
    title: "OpenCanal Core Ontology v0.2",
    source_type: "ontology",
    excerpt: "Accepted claims require evidence or moderator rationale; out-of-mandate claims must be flagged.",
    confidence: 0.92
  }
];
