# BEBECIEN Product Agent PRD v0.1

> Phase: 2  
> Role: first applied commercial vertical after Agent Debate Room  
> Protocol dependency: `agent_debate_room_prd_v0_1.md`

## 1. Goal

Build the first applied OpenCanal Business Agent for BEBECIEN, a baby-product commerce business. The agent helps parents and consumers ask product questions, compare conditions, receive evidence-backed recommendations, and escalate risky questions to a human reviewer.

BEBECIEN is no longer the first proof of OpenCanal's essence. The first proof is Agent Debate Room. BEBECIEN applies the same claim/evidence/counterclaim/review/receipt protocol to commerce.

Consumers use this flow for free. BEBECIEN is the business customer.

## 2. Users

### Parent / Consumer

Needs:

- ask product questions in natural language
- provide baby age/month, purpose, budget, material preferences, and shipping needs
- see recommendations with evidence and cautions
- know when a human review is required

Not needed in v0.1:

- paid consumer subscription
- medical diagnosis
- automatic purchase execution
- storing sensitive medical data

### BEBECIEN Operator

Needs:

- register and edit products
- define product evidence, age suitability, materials, certificates, cautions, shipping, and exchange/refund policy
- review high-risk or uncertain answers
- inspect recommendation history and Evidence Receipts
- correct agent answers and improve the knowledge base

## 3. Core Flow

```text
Parent question
-> ParentIntent extraction
-> Safety classification
-> Product/policy evidence retrieval
-> Recommendation or human escalation
-> Human approval/edit/reject
-> Evidence Receipt
-> Dashboard metrics update
```

## 4. Product Knowledge Base

Each product should include:

- product_id
- name
- category
- target_age_months_min
- target_age_months_max
- use_cases
- materials
- certificates
- safety_cautions
- contraindications
- price
- stock_status
- shipping_policy
- exchange_refund_policy
- evidence_sources
- official_url
- last_verified_at

## 5. ParentIntent

Fields:

- question_text
- child_age_months
- child_age_years
- purchase_purpose
- budget_max_krw
- preferred_materials
- avoid_materials
- gift_context
- desired_shipping_speed
- sensitivity_notes
- public_context_only

Sensitive or high-risk free text must not be treated as medical truth. It should be classified for human review where needed.

## 6. Safety Rules

Always block or escalate:

- medical diagnosis
- allergy safety guarantees
- developmental delay advice
- disease treatment claims
- "100% safe" style absolute safety claims
- product use below minimum age/month
- refund/exchange final approval
- stock guarantee when stock_status is not confirmed

Allowed with evidence:

- product category explanation
- age/month suitability based on product metadata
- material and certificate explanation
- shipping policy summary
- exchange/refund policy summary
- comparison among BEBECIEN products
- gift-oriented recommendation

## 7. Recommendation Response

Each response must include:

- short answer
- recommended products, maximum 3
- reason for each recommendation
- evidence source
- caution or not-suitable note
- human review status
- receipt availability

If evidence is missing, the agent must say it cannot confirm and route to human review.

## 8. Human Review Queue

Review statuses:

- pending
- approved
- edited
- rejected
- blocked

Reviewer actions:

- approve answer
- edit answer
- reject answer
- mark unsafe
- request product data update
- create Evidence Receipt

## 9. Evidence Receipt

Receipt fields:

- receipt_id
- question_text
- parent_intent_snapshot
- agent_id
- recommended_products
- evidence_snapshot
- cautions
- reviewer_action
- transcript_hash
- agent_version
- created_at
- status

Receipt statuses:

- draft
- approved
- rejected
- expired
- disputed

## 10. MVP Acceptance Criteria

- 30 or more BEBECIEN products can be represented.
- 50 parent question scenarios can run end to end.
- Every recommendation has evidence.
- Unsafe questions are escalated or blocked.
- Human reviewer can edit and approve an answer.
- Approved answer can generate an Evidence Receipt.
- Dashboard shows inquiry count, evidence coverage, human revision count, and blocked count.
