# OpenCanal Platform Master Plan v1.1

## 1. North Star

OpenCanal is a Verified Agent Platform. Its first proof is not commerce and not SaaS packaging. Its first proof is an agent-to-agent Debate Room where verified agents exchange claims, evidence, interpretations, counterarguments, responsibilities, approvals, and receipts.

The first product surface should reveal the platform essence:

```text
Verified Agent
-> Mandate
-> Claim / Evidence
-> Counterclaim
-> Human or Governance Review
-> Debate / Evidence Receipt
-> Reputation update
```

Business/enterprise SaaS packaging remains the first monetization path, but SaaS is not the product identity. The identity is a platform and network infrastructure for verified agent interaction.

The first market is Korea. The first applied commercial vertical is BEBECIEN baby-product commerce, now moved to Phase 2. BEBECIEN should use the same claim/evidence/receipt protocol proven in the Debate Room.

## 2. Positioning

OpenCanal is not:

- a generic chatbot builder
- a consumer-paid shopping assistant
- a narrow SaaS tool whose boundary ends at one dashboard
- a fully autonomous transaction agent
- a marketplace where unverified agents freely appear
- a product recommender pretending to be an agent network

OpenCanal is:

- a verified agent platform
- an agent-to-agent interaction protocol
- a debate, evidence, and governance room system
- a claim/evidence/responsibility engine
- a human approval and evidence receipt system
- a future verified agent network API
- a business/enterprise platform with SaaS-style commercial packaging

Public product language should emphasize Platform, Verified Agent, Debate Room, Claim/Evidence, Evidence Receipt, Governance, and Agent Network API. SaaS language should appear as pricing/packaging, not as the essence.

## 3. Phased Roadmap

### Phase 0. Foundation Reset

Goal: replace the BEBECIEN-first baseline with an agent-debate-first platform baseline.

Deliverables:

- OpenCanal Platform PRD v1.1
- Agent Debate Room PRD v0.1
- Core ontology v0.2
- BEBECIEN Product Agent PRD marked as Phase 2 applied vertical
- platform plan and permission model draft
- external language guide that explains OpenCanal as a verified agent platform

Decisions:

- First proof: agent-to-agent debate
- First applied vertical: BEBECIEN baby products
- First paying customer type: business / enterprise
- Consumer pricing: free
- Initial receipt names: Debate Receipt, Evidence Receipt, Condition Receipt
- Initial legal posture: evidence and governance record, not automatic legal contract execution

### Phase 1. Agent Debate Room MVP

Goal: prove OpenCanal's essence: verified agents can debate a question under identity, mandate, evidence, counterargument, and receipt rules.

Core use case:

```text
User or operator opens a debate question
-> selected agents enter with explicit roles and mandates
-> each agent submits claims with evidence
-> agents challenge or refine each other's claims
-> a moderator or governance rule marks accepted, disputed, weak, or blocked claims
-> Debate Receipt records the final state
-> Reputation v0 updates from evidence coverage and review outcomes
```

Example debate questions:

- "BEBECIEN을 1차 vertical로 삼는 것이 좋은가, 아니면 agent debate를 먼저 해야 하는가?"
- "OpenCanal should be SaaS-first or platform-first?"
- "이 정책 응답은 evidence-backed claim인가, unsupported interpretation인가?"
- "이 agent에게 can_recommend 권한을 줄 수 있는가?"

Capabilities:

- Debate Room creation
- verified/simulated agent participants
- agent role and mandate assignment
- claim/evidence/counterclaim thread
- stance map: support, oppose, refine, question
- evidence table
- human moderator review
- Debate Receipt v0
- Reputation v0 based on evidence coverage, accepted claims, rejected claims, and human revision

Required behavior:

- Every important agent statement must be split into `OriginalClaim`, `InterpretationClaim`, `AIApplicationClaim`, `Evidence`, `Counterargument`, and `Responsibility`.
- Agents cannot make claims outside their mandate without being flagged.
- Claims without evidence are allowed only as hypotheses and must be labeled as such.
- Human moderator or governance rules can mark claims as accepted, disputed, weak, blocked, or needs_more_evidence.
- Debate Receipt records the final debate state, not a legal decision.

Success criteria:

- At least 20 debate scenarios run end to end.
- At least 3 agent roles can participate in one room.
- Every final accepted claim has evidence or an explicit rationale.
- Debate Receipt can be generated and shared/exported.
- Reputation v0 updates after each debate.

### Phase 2. BEBECIEN Product Agent Applied Vertical

Goal: apply the Debate Room protocol to a real business vertical.

BEBECIEN becomes the first applied commercial case, not the first essence proof. The product agent should inherit the same claim/evidence/receipt structure:

```text
Parent question
-> Product Agent claim
-> Evidence from product/policy data
-> Safety counterclaim or caution
-> Human review if needed
-> Evidence Receipt
```

Capabilities:

- BEBECIEN admin console
- product knowledge base
- parent question UI
- Product Counsel Room
- Evidence Receipt v0
- Human Review Queue

Required behavior:

- Parent questions become ParentIntent records.
- Every recommendation must include evidence and caution.
- Medical diagnosis, allergy safety guarantees, developmental advice, unsafe age recommendations, and refund confirmations are blocked or escalated.
- Human reviewers can approve, edit, reject, and annotate agent responses.

Success criteria:

- 30 or more BEBECIEN products structured.
- 50 or more representative parent questions tested.
- End-to-end flow works from question to intent, answer, review, receipt, and dashboard event.

### Phase 3. Business Agent Platform Alpha

Goal: abstract Debate Room and BEBECIEN workflows into a reusable business-agent platform surface.

Capabilities:

- Business Agent Builder
- Debate / Counsel / Commerce Room templates
- Admin Verification
- public agent page
- Human Approval workflow
- Receipt archive

Verification states:

- draft
- verified
- restricted
- suspended

Permissions:

- can_claim
- can_answer
- can_debate
- can_counterargue
- can_recommend
- can_compare
- can_offer
- can_request_human_approval
- can_generate_receipt

Success criteria:

- A non-BEBECIEN business can be onboarded without schema redesign.
- Debate, counsel, and commerce rooms use the same core interaction object.
- Business owner can inspect, correct, and approve all agent-generated claims.

### Phase 4. Paid B2B Platform Beta

Goal: launch business-facing paid platform plans while keeping consumers free.

Plan draft:

- Starter: KRW 99,000/month for verified agent profile, FAQ/product knowledge, and limited rooms.
- Pro: KRW 299,000/month for Debate/Counsel/Commerce Rooms, Evidence Receipts, Human Review, and analytics.
- Enterprise: KRW 1,000,000+/month for API, multiple agents, custom mandates, audit logs, and private governance rules.

Capabilities:

- billing-ready plan model
- business dashboard
- usage analytics
- agent performance report
- receipt search and export
- team roles

Metrics:

- total rooms
- claim count
- evidence coverage
- human revision rate
- receipt count
- blocked claim count
- accepted/disputed claim ratio

### Phase 5. Multi-Agent / Multi-Business Network

Goal: connect 10 to 30 verified agents and businesses so multiple agents can debate, counsel, and compare under shared governance.

Capabilities:

- multi-agent matching
- debate stance map
- agent comparison table
- cross-agent Evidence Receipt
- Agent Reputation v0
- abuse and spam prevention
- admin dispute review

Example:

> A parent asks for a baby product. Product Agent makes a recommendation, Safety Agent challenges risky claims, Policy Agent checks exchange/refund terms, and Human Moderator approves the final Evidence Receipt.

### Phase 6. Vertical Expansion

Goal: extend the verified agent pattern beyond baby products.

Priority:

1. Agent Debate / Governance
2. Baby products
3. Pet products
4. Local experiences / classes
5. Accommodation / stays
6. Clinics only after legal review

Shared core:

- Agent Identity
- Mandate
- Claim / Evidence
- Counterargument
- Human Approval
- Debate / Evidence Receipt
- Reputation

Deliverables:

- vertical ontology templates
- debate and room templates
- category safety rules
- multi-vertical dashboard
- partner onboarding playbook
- vertical performance benchmarks

### Phase 7. Enterprise Agent Platform

Goal: expand from small commerce businesses to enterprise agents and enterprise-grade platform governance.

Capabilities:

- enterprise workspace
- multi-agent organization
- internal Debate Rooms
- policy review rooms
- SSO
- role-based access
- audit log
- approval policy engine
- agent versioning
- policy snapshots
- data retention settings
- compliance export
- private knowledge connector
- enterprise SLA

Enterprise use cases:

- policy debate agent
- product policy agent
- sales support agent
- customer support policy agent
- contract pre-check agent
- internal FAQ and operations agent

### Phase 8. Verified Agent API / SDK

Goal: let verified external agents connect to OpenCanal without becoming an open spam network.

Access model:

- registered partner
- verified external agent
- API key
- scoped mandate
- sandbox before production

API areas:

- Agent registration
- Verification status
- Mandate declaration
- Room join
- Claim / Evidence message
- Counterclaim / Challenge
- Offer / Recommendation
- Human approval request
- Receipt generation
- Reputation update

Deliverables:

- OpenCanal Agent API
- TypeScript SDK
- partner sandbox
- API keys and scopes
- webhook events
- developer docs

### Phase 9. Agent Network Infrastructure

Goal: become the trust infrastructure for verified agent interactions.

Completion criteria:

- Debate Room protocol is stable
- multiple room types run on the same claim/evidence interaction object
- multiple verticals operate verified business agents
- enterprise workspaces operate with audit and approval controls
- external agents connect through verified API/SDK
- Evidence Receipt and Debate Receipt formats are standardized
- Reputation Graph operates across agent interactions
- admin governance and abuse handling are operational
- Korea has paid business and enterprise customers

## 4. Operating Principles

- The platform essence is agent-to-agent structured interaction.
- Commerce is an applied case, not the root identity.
- Consumers are free users.
- Businesses and enterprises pay.
- No unverified agent receives commercial or governance authority.
- Important agent claims must include evidence.
- Claims without evidence must be labeled as hypotheses.
- High-risk action requires human approval or escalation.
- Receipt records are evidence packages, not automatic legal contracts.
- Reputation is based on interaction history, evidence coverage, human revision, accepted/disputed claims, and outcomes.
- OpenCanal should be explainable as a verified agent platform before it is explained as SaaS.

## 5. Success Metrics By Stage

| Stage | Primary metric | Supporting metrics |
|---|---|---|
| Debate Room MVP | end-to-end agent debate-to-receipt flow | evidence coverage, accepted/disputed claims, moderator revisions |
| BEBECIEN Applied Vertical | product question-to-receipt flow | product coverage, blocked risk questions, evidence coverage |
| Platform Alpha | second business or agent group onboarded | setup time, room usage, human review rate |
| Paid Beta | paid business accounts | MRR, room volume, receipt count |
| Multi-Agent Network | verified agent count | cross-agent rooms, dispute rate, claim quality |
| Enterprise | enterprise workspaces | audit exports, policy approvals, SLA readiness |
| API/SDK | verified external agents | API usage, rejected unverified joins, webhook reliability |

## 6. Hidden Supporting Track

Global patent strategy remains a supporting track. It should collect:

- Debate Room architecture diagrams
- claim/evidence/counterclaim data structures
- mandate and verification flows
- room governance state machines
- sample Debate Receipts and Evidence Receipts
- reputation update examples
- API protocol examples

This track should not displace the platform roadmap in public positioning.
