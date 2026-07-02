# OpenCanal — Cross-User Authorization Boundary Test (test2-authz)

- **Date:** 2026-06-14
- **Target:** OpenCanal Next.js API @ `http://localhost:3000` (local dev, developer's own app)
- **Mode:** Read + black-box test only. No source was modified.
- **Auth:** dev-email credentials login (CSRF → `/api/auth/callback/dev-email` → session). Admin = `ghddudxor12@gmail.com` (via `ADMIN_EMAILS`). Runner = pairing code → `deviceToken` → `Bearer` on `/api/runner/*`.
- **Actors:** User A, User B, User C (non-party, for receipt test), Admin. All emails unique `t2-authz-<rand>@test.com`.
- **Method:** Build A's and B's resources, then attack as the other user / wrong runner token. A 2xx where a 4xx is expected = FINDING.

## Scope summary

**Result: All authorization boundaries held. 0 findings.** Every cross-user attack was correctly rejected with the expected 4xx/redirect. Ownership is enforced at the data layer (owner-id / participant / device-agent checks) on every route, not merely existence — IDOR probes with valid-but-not-owned cuid ids were rejected identically to bogus ids.

## Results table

| # | Attack | Method + Path | Expected | Actual | Verdict | Severity | Suggested fix |
|---|--------|---------------|----------|--------|---------|----------|---------------|
| 1a | B creates pairing for A's agent | POST `/api/agents/:Aagent/pairing` | 403 | 403 `forbidden` | PASS | high | none |
| 1b | B requests verification for A's agent | POST `/api/agents/:Aagent/verification` | 403 | 403 `forbidden` | PASS | med | none |
| 1c | B PATCH A's agent permissions | PATCH `/api/agents/:Aagent/permissions` | 403 | 403 `forbidden` | PASS | high | none |
| 2a | B posts instruction into A-only room | POST `/api/rooms/:roomId/instructions` | 403 | 403 `not a participant` | PASS | high | none |
| 2b | B reads messages of A-only room | GET `/api/rooms/:roomId/messages` | 403/404 | 403 `forbidden` | PASS | high | none |
| 2c | B closes A-only room | PATCH `/api/rooms/:roomId` | 403 | 403 `forbidden` | PASS | med | none |
| 3 | B decides approval owned by A's agent | POST `/api/approvals/:approvalId` | 403 | 403 `forbidden` | PASS | critical | none |
| 4a | A confirms A's own proposal | POST `/api/rooms/:roomId/receipts` | 403 | 403 `상대의 제안만…` | PASS | med | none |
| 4b | C (non-party) opens receipt page | GET `/receipts/:id` | redirect/403 | 307 → `/rooms` (party A/B = 200) | PASS | med | none |
| 5a | A's runner token posts into B-only room | POST `/api/runner/messages` | 403 | 403 `not in room` | PASS | critical | none |
| 5b | A's token attests B's source | POST `/api/runner/sources/:sourceId/attest` | 404 | 404 `source not found` | PASS | high | none |
| 5c | A's token fails B's instruction | POST `/api/runner/instructions/:id/fail` | 404 | 404 `instruction not found` | PASS | high | none |
| 5d | A's inbox returns only A's items | GET `/api/runner/inbox` | no B data | clean (agent=A, no B room/instr) | PASS | high | none |
| 5e | Reuse pairing code 2nd time | POST `/api/runner/pair` | 400 | 400 `invalid or expired code` | PASS | high | none |
| 5f | Garbage Bearer on inbox | GET `/api/runner/inbox` | 401 | 401 `unauthorized` | PASS | high | none |
| 5f2 | Empty Bearer on inbox | GET `/api/runner/inbox` | 401 | 401 `unauthorized` | PASS | high | none |
| 6a | Normal user B hits admin endpoint | POST `/api/admin/verification/:id` | 403 | 403 `forbidden` | PASS | critical | none |
| 6b | Role escalation via body `{role:"admin"}` | POST `/api/auth/callback/dev-email` | role stays user | session role=`user`, admin endpoint=403 | PASS | critical | none |
| 7a | IDOR: B PATCH A2's perms (valid id) | PATCH `/api/agents/:A2agent/permissions` | 403 | 403 `forbidden` | PASS | high | none |
| 7b | IDOR: B confirms in A-only trade room (valid roomId) | POST `/api/rooms/:roomId/receipts` | 403/404 | 403 `forbidden` | PASS | high | none |
| 7c | IDOR: B's token fails A's instruction (valid id) | POST `/api/runner/instructions/:id/fail` | 404 | 404 `instruction not found` | PASS | high | none |

## Boundaries that held (with code reference)

- **Agent ownership** — `userOwnsAgent(user.id, agentId)` in `apps/web/src/lib/session.ts` gates pairing, verification request, and permissions PATCH (`apps/web/src/app/api/agents/[agentId]/...`).
- **Room participation** — `room.participants.find(p => p.agent.ownerId === user.id)` gates instructions POST, messages GET, and room PATCH (`apps/web/src/app/api/rooms/[roomId]/...`). Held messages (`approval` pending/rejected) are only returned to the sender's owner.
- **Approval ownership** — `approval.agent.ownerId !== user.id → 403` (`apps/web/src/app/api/approvals/[approvalId]/route.ts`).
- **Receipt confirm** — requires room participation AND `proposal.sender.ownerId !== user.id` (can't self-confirm) AND approved status (`apps/web/src/app/api/rooms/[roomId]/receipts/route.ts`).
- **Receipt page** — `requireUser()` + `isParty` check, non-party redirected to `/rooms` (`apps/web/src/app/receipts/[receiptId]/page.tsx`).
- **Runner token scoping** — `authenticateRunner` resolves a single agent by SHA-256 token hash; all `/api/runner/*` routes filter by `device.agentId`. Messages require `roomParticipant` for that agent; attest/fail require the resource's `agentId === device.agentId`. Inbox queries are scoped to the device's agent.
- **Pairing single-use** — code is marked `consumedAt` on pair; reuse → 400. Codes also expire after 10 min.
- **Admin** — `user.role !== "admin" → 403` (`apps/web/src/app/api/admin/verification/[requestId]/route.ts`). Role is derived server-side from `ADMIN_EMAILS` in the NextAuth `jwt` callback (`apps/web/src/auth.ts`); the `dev-email` credentials provider only reads `email`/`name`, so a client-supplied `role` field is ignored.

## Top 3 risks (residual / defense-in-depth, NOT findings)

1. **Dev-login is the only authn gate in this environment.** `ALLOW_DEV_LOGIN=true` lets anyone log in as any email — including the admin email `ghddudxor12@gmail.com` — with no password. This is expected for local dev (and the code disables it in production via `NODE_ENV`), but if this env ever faces a network, admin takeover is trivial. Ensure `ALLOW_DEV_LOGIN` is never set in a deployed/shared environment.
2. **Information-leak asymmetry across routes.** Some not-yours resources return `403` (rooms, agents, approvals) while others return `404` (runner attest/fail, A-only receipt confirm). Both are safe, but the 403-vs-404 split can let an attacker distinguish "exists but not mine" from "does not exist" (resource-enumeration oracle). Consider standardizing on 404 for cross-tenant denials where existence itself is sensitive.
3. **No per-token rate limiting on runner endpoints observed.** Authorization is solid, but `/api/runner/inbox` / `pair` have no visible throttling, leaving room for token brute-force or drain abuse. Per-device and per-IP rate limits would harden against automated attacks. (Owner instructions are rate-limited per room/hour; runner reads are not.)

## Notes / test mechanics

- Confirming a receipt requires a **cross-owner** room (proposal sender's owner ≠ confirmer), so same-owner trade rooms can never produce a receipt. The 4b non-party test therefore used a third user C against an A↔B receipt.
- The instructions route assigns an instruction to the *first* room participant owned by the caller; this matters only for test setup, not for security.
- Harness: `tmp-authz2/harness.mjs` (scenarios 1–3, 4a, 5–7) + `tmp-authz2/receipt4b.mjs` (scenario 4b). Both deleted after the run.
