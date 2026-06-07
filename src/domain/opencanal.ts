export type AgentType = "business" | "parent" | "enterprise" | "admin" | "external";

export type VerificationStatus = "draft" | "verified" | "restricted" | "suspended";

export type VerificationLevel =
  | "L0_simulation"
  | "L1_self_declared"
  | "L2_owner_verified"
  | "L3_business_verified"
  | "L4_enterprise_verified"
  | "L5_authority_verified";

export type RoomStatus = "draft" | "active" | "under_review" | "receipt_ready" | "closed";

export type DebateRole = "proponent" | "opponent" | "evidence" | "governance" | "moderator";

export type DebateStance = "support" | "oppose" | "refine" | "question" | "neutral";

export type RiskLevel = "low" | "medium" | "high" | "blocked";

export type ReviewStatus =
  | "pending"
  | "accepted"
  | "disputed"
  | "weak"
  | "needs_more_evidence"
  | "out_of_mandate"
  | "blocked";

export type MandateAction =
  | "can_answer"
  | "can_claim"
  | "can_debate"
  | "can_counterargue"
  | "can_recommend"
  | "can_compare"
  | "can_offer"
  | "can_request_human_approval"
  | "can_generate_receipt";

export type EvidenceSource = {
  source_id: string;
  title: string;
  source_type: "prd" | "ontology" | "policy" | "scenario" | "moderator_rationale";
  excerpt: string;
  confidence: number;
};

export type Agent = {
  agent_id: string;
  agent_type: AgentType;
  display_name: string;
  role: DebateRole;
  owner_id: string;
  verification_status: VerificationStatus;
  verification_level: VerificationLevel;
  version: string;
  reputation_id: string;
};

export type Mandate = {
  mandate_id: string;
  agent_id: string;
  allowed_actions: MandateAction[];
  scope: string;
  human_approval_required: boolean;
};

export type DebateClaim = {
  claim_id: string;
  room_id: string;
  agent_id: string;
  stance: DebateStance;
  original_claim: string;
  interpretation_claim: string;
  ai_application_claim: string;
  evidence: EvidenceSource[];
  counterarguments: string[];
  responsibility: string;
  mandate_check: "in_mandate" | "out_of_mandate" | "unclear";
  risk_level: RiskLevel;
  review_status: ReviewStatus;
  is_hypothesis: boolean;
  moderator_rationale?: string;
  created_at: string;
};

export type ReviewEvent = {
  event_id: string;
  claim_id: string;
  reviewer_agent_id: string;
  from_status: ReviewStatus;
  to_status: ReviewStatus;
  note: string;
  created_at: string;
};

export type DebateRoom = {
  room_id: string;
  title: string;
  debate_question: string;
  room_type: "debate";
  participants: string[];
  mandates: Mandate[];
  claims: DebateClaim[];
  evidence_table: EvidenceSource[];
  stance_map: Record<DebateStance, string[]>;
  review_events: ReviewEvent[];
  debate_receipt_id?: string;
  status: RoomStatus;
  created_at: string;
};

export type DebateReceipt = {
  receipt_id: string;
  room_id: string;
  debate_question: string;
  participating_agents: string[];
  mandate_snapshot: Record<string, Mandate>;
  accepted_claims: DebateClaim[];
  disputed_claims: DebateClaim[];
  blocked_claims: DebateClaim[];
  evidence_snapshot: Record<string, EvidenceSource>;
  moderator_summary: string;
  transcript_hash: string;
  agent_versions: Record<string, string>;
  status: "draft" | "approved" | "rejected" | "expired" | "disputed";
  created_at: string;
};

export type ReputationGraph = {
  reputation_id: string;
  agent_id: string;
  response_count: number;
  receipt_count: number;
  evidence_coverage_rate: number;
  human_revision_rate: number;
  blocked_response_count: number;
  dispute_count: number;
  last_updated: string;
};

export type DebateRunResult = {
  room: DebateRoom;
  receipt: DebateReceipt;
  reputation: ReputationGraph[];
};

export type AgentRuntime = {
  runOpeningClaim(agent: Agent, room: DebateRoom): DebateClaim;
  runCounterClaim(agent: Agent, room: DebateRoom, target: DebateClaim): DebateClaim;
  runEvidenceCheck(agent: Agent, room: DebateRoom): DebateClaim;
  runGovernanceReview(agent: Agent, room: DebateRoom): DebateClaim;
  generateModeratorSummary(agent: Agent, room: DebateRoom): string;
};
