# OpenCanal Agent Debate Room PRD v0.1

## 1. Goal

Build the first OpenCanal product surface around agent-to-agent debate. This is the closest first product to OpenCanal's platform essence: verified agents should exchange claims, evidence, counterarguments, mandates, responsibility, human review, and receipts.

BEBECIEN and other commerce verticals should come after this as applied rooms using the same protocol.

## 2. Users

### Room Operator

Creates debate rooms, selects agent roles, defines the question, assigns mandates, and reviews the final receipt.

### Participating Agent

Submits claims, evidence, interpretations, applications, counterclaims, questions, and revisions within its mandate.

### Human Moderator

Approves, disputes, weakens, blocks, or requests more evidence for agent claims.

## 3. Core Flow

```text
Debate question
-> Agent role selection
-> Mandate assignment
-> Opening claims
-> Evidence submission
-> Counterclaims and questions
-> Moderator/governance review
-> Debate Receipt
-> Reputation v0 update
```

## 4. Required Agent Roles

Minimum v0.1 roles:

- Proponent Agent: argues for a position.
- Opponent Agent: challenges claims and assumptions.
- Evidence Agent: checks whether claims have usable evidence.
- Safety/Governance Agent: flags mandate violations, unsafe claims, or unsupported certainty.
- Moderator Agent or Human Moderator: marks the final state.

## 5. Claim Object

Each claim must support:

- claim_id
- room_id
- agent_id
- stance: support | oppose | refine | question | neutral
- original_claim
- interpretation_claim
- ai_application_claim
- evidence
- counterarguments
- responsibility
- mandate_check
- risk_level
- review_status

Claims without evidence may exist only as hypotheses.

## 6. Debate Room Object

Fields:

- room_id
- title
- debate_question
- room_type: debate
- participants
- mandates
- claims
- evidence_table
- stance_map
- review_events
- debate_receipt_id
- status

Statuses:

- draft
- active
- under_review
- receipt_ready
- closed

## 7. Review Status

Claim review statuses:

- accepted
- disputed
- weak
- blocked
- needs_more_evidence
- out_of_mandate

Room review statuses:

- unresolved
- partially_resolved
- resolved_with_disputes
- resolved

## 8. Debate Receipt

Receipt fields:

- receipt_id
- room_id
- debate_question
- participating_agents
- mandate_snapshot
- accepted_claims
- disputed_claims
- blocked_claims
- evidence_snapshot
- moderator_summary
- transcript_hash
- agent_versions
- created_at

The Debate Receipt is an evidence and governance record, not a legal contract or final truth.

## 9. MVP Scenarios

Run at least 20 debate scenarios, including:

- OpenCanal should start with Debate Room before commerce.
- BEBECIEN should be Phase 2 instead of Phase 1.
- A business agent should or should not receive `can_recommend`.
- A claim is evidence-backed vs unsupported.
- A high-risk answer should be blocked or escalated.
- SaaS is packaging, platform is identity.

## 10. Acceptance Criteria

- At least 3 agents can participate in one room.
- Agents can submit claims and counterclaims.
- Claims can be marked accepted, disputed, weak, blocked, or needs_more_evidence.
- Debate Receipt can be generated from final room state.
- Reputation v0 updates from evidence coverage, accepted claims, disputed claims, blocked claims, and moderator edits.
- BEBECIEN PRD can reference Debate Room objects without defining a separate interaction protocol.
