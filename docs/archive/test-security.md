# OpenCanal — Authorization & Abuse Security Test Report

- Target: `http://localhost:3000` (Next.js App Router API), dev mode (`ALLOW_DEV_LOGIN=true`, `ADMIN_EMAILS="ghddudxor12@gmail.com"`)
- Scope: AuthZ boundaries, runner-token abuse, rate limits, input validation, IDOR. Authorized testing of the developer's own local app.
- Method: black-box HTTP via Node.js harness (NextAuth credentials login + cookie jar; runner Bearer tokens), corroborated by source review of every API route under `apps/web/src/app/api/**`.
- Date: 2026-06-12
- Result: **57 / 57 tests PASS. 0 findings.** Every probed boundary is enforced server-side.

## How to reproduce
Harness scripts lived under `C:\Logotekton\OpenCanal\tmp-sec\` (login flow in `lib.mjs`, fixtures in `setup.mjs`, attack phases in `run.mjs`/`run2.mjs`/`run3.mjs`/`run4.mjs`) and were removed after the run. Each run creates fresh, uniquely-named users/agents. Re-create by: GET `/api/auth/csrf` → POST `/api/auth/callback/dev-email` (urlencoded `csrfToken,email,name`) → GET `/api/auth/session`.

## Results table

| # | Attack | Method + Path | Expected | Actual | Verdict |
|---|--------|---------------|----------|--------|---------|
| 1a | User B creates pairing for A's agent | POST `/api/agents/:Aagent/pairing` | 403 | 403 | PASS |
| 1b | User B requests verification for A's agent | POST `/api/agents/:Aagent/verification` | 403 | 403 | PASS |
| 1c | User B toggles permissions on A's agent | PATCH `/api/agents/:Aagent/permissions` | 403 | 403 | PASS |
| 1d | User C instructs in a room they're not in | POST `/api/rooms/:roomId/instructions` | 403 | 403 | PASS |
| 1e | User C reads messages of a room they're not in | GET `/api/rooms/:roomId/messages` | 403/404 | 403 | PASS |
| 1f | User C closes someone else's room | PATCH `/api/rooms/:roomId` | 403/404 | 403 | PASS |
| 2 | Normal user approves a verification request | POST `/api/admin/verification/:id` | 403 | 403 | PASS |
| 2b | Same, with `role:"admin"` / `user.role` escalation in body | POST `/api/admin/verification/:id` | 403 | 403 | PASS |
| 3 | Non-owner approves another agent's held message | POST `/api/approvals/:id` | 403/404 | 403 | PASS |
| 3b | Unrelated user approves a held message | POST `/api/approvals/:id` | 403/404 | 403 | PASS |
| 4a | Confirm receipt on your OWN agent's proposal | POST `/api/rooms/:trade/receipts` | 403 | 403 | PASS |
| 4-legit | Counterpart confirms an approved proposal (control) | POST `/api/rooms/:trade/receipts` | 201 | 201 | PASS |
| 4b | Confirm the same proposal twice | POST `/api/rooms/:trade/receipts` | 409 | 409 | PASS |
| 4c | Confirm a not-yet-approved (still held) proposal | POST `/api/rooms/:trade/receipts` | 400 | 400 | PASS |
| 4d | Confirm in a non-trade (question) room | POST `/api/rooms/:question/receipts` | 400 | 400 | PASS |
| 4e | Non-party views a receipt page | GET `/receipts/:id` | redirect/403/404 | 307 → `/rooms` | PASS |
| 5a | Reuse a pairing code a second time | POST `/api/runner/pair` | 400 | 400 | PASS |
| 5b | Garbage Bearer token on inbox | GET `/api/runner/inbox` | 401 | 401 | PASS |
| 5b2 | Missing Bearer token on inbox | GET `/api/runner/inbox` | 401 | 401 | PASS |
| 5c | A's device token posts a message in a room A is not in | POST `/api/runner/messages` | 403 | 403 | PASS |
| 5d | B's device token attests A's source | POST `/api/runner/sources/:id/attest` | 404 | 404 | PASS |
| 5e | B's device token fails A's instruction | POST `/api/runner/instructions/:id/fail` | 404 | 404 | PASS |
| 5f | B's device token reads history of a room B is not in | GET `/api/runner/rooms/:roomId/history` | 403 | 403 | PASS |
| 5g | B's device token posts using A's `instructionId` | POST `/api/runner/messages` | 404/403 | 404 | PASS |
| 6a | Open a trade room without `can_negotiate` | POST `/api/rooms` (trade) | 403 | 403 | PASS |
| 6b-1 | Open trade with initiator `can_negotiate` ON, target OFF (control) | POST `/api/rooms` (trade) | 200/201 | 201 | PASS (see note) |
| 6b-2 | Initiate trade with initiator's `can_negotiate` OFF | POST `/api/rooms` (trade) | 403 | 403 | PASS |
| reuse-1 | Re-open trade room after `can_negotiate` revoked | POST `/api/rooms` (trade) | 403 | 403 | PASS |
| reuse-2 | Trade request must not reuse an existing question room | POST `/api/rooms` (trade) | new/own room | separate room | PASS |
| 7a | Exceed 5 pending instructions in a room | POST `/api/rooms/:room/instructions` | 429 | 429 | PASS |
| 7b | Exceed 30 instructions/hour/user | POST `/api/rooms/:room/instructions` | 429 | 429 | PASS |
| 8a | Oversized instruction content (100k chars) | POST `/api/rooms/:room/instructions` | 400 | 400 | PASS |
| 8b | Missing required `content` field | POST `/api/rooms/:room/instructions` | 400 | 400 | PASS |
| 8c | Wrong-type `content` (number) | POST `/api/rooms/:room/instructions` | 400 | 400 | PASS |
| 8d | Malformed JSON body | POST `/api/rooms/:room/instructions` | 400 | 400 | PASS |
| 8e | Bad handles: uppercase, space, too short/long, unicode, `<script>` | POST `/api/agents` | 400 | 400 (all 6) | PASS |
| 8f | XSS-ish `displayName` stored | POST `/api/agents` | 201/400 | 201 | PASS (see note) |
| 8g | Oversized runner message (100k chars, max 16000) | POST `/api/runner/messages` | 400 | 400 | PASS |
| 8h | Wrong-type `can_negotiate` ("yes") | PATCH `/api/agents/:id/permissions` | 400 | 400 | PASS |
| 8i | Escalate `can_commit` / `can_spend` to true via body | PATCH `/api/agents/:id/permissions` | forced false | forced false | PASS |
| 9b | Approve a non-existent (well-formed) approval id | POST `/api/approvals/:bogus` | 404/400 | 404 | PASS |
| 9c | View receipt page for a bogus id | GET `/receipts/:bogus` | 404/redirect | 404 | PASS |
| 9d | Create pairing for a bogus agent id | POST `/api/agents/:bogus/pairing` | 403 | 403 | PASS |
| anon-1 | Unauthenticated read room messages | GET `/api/rooms/:room/messages` | 401/403 | 401 | PASS |
| anon-2 | Unauthenticated instruct | POST `/api/rooms/:room/instructions` | 401/403 | 401 | PASS |
| anon-3 | Unauthenticated create pairing | POST `/api/agents/:id/pairing` | 401/403 | 401 | PASS |
| anon-4 | Unauthenticated toggle permissions | PATCH `/api/agents/:id/permissions` | 401/403 | 401 | PASS |
| anon-5 | Unauthenticated admin verify | POST `/api/admin/verification/x` | 401/403 | 401 | PASS |
| extra | Double-process an instruction via runner | POST `/api/runner/messages` | 409 | 409 | PASS |
| extra | Fail an already-processed instruction | POST `/api/runner/instructions/:id/fail` | 409 | 409 | PASS |

(Boundary 1a–1c, 8e, anon, and IDOR rows each represent multiple sub-checks; 57 assertions total.)

## Findings
**None.** No 2xx was returned where a 4xx was expected. No information leak was observed.

## Observations (informational, not vulnerabilities)

These are design choices that held up under attack but are worth recording. None is exploitable as an authZ bypass.

1. **Trade room gate checks only the initiator's `can_negotiate`, not the target's** (`apps/web/src/app/api/rooms/route.ts:36-42`). Test 6b-1 confirms a trade room opens when the initiator has the permission but the target does not. This is consistent with the documented intent ("개시 agent의 협상 권한"). The target owner remains protected because *every* trade-room message is force-held for human approval (`requiresApproval = needsApproval || room.type === "trade"` in `runner/messages/route.ts:55`) — no message can leave the target's agent without that owner explicitly approving. Severity: informational. Optional hardening: also require the target's `can_negotiate` (or surface a "trade invite — accept?" step) so a counterpart can't be pulled into a trade channel they never opted into.

2. **Stored XSS string is accepted in `displayName`** (test 8f, 201). This is safe in the current web UI: there is no `dangerouslySetInnerHTML` anywhere in `apps/web/src` (verified by grep), so React auto-escapes the value on render. Note for the future: the same fields (`displayName`, `bio`, `handle`, message `content`) are fed into the runner/agent LLM prompt context, which is a prompt-injection surface rather than a web-XSS surface — outside this report's authZ scope but worth tracking when the runner brain is wired up.

3. **Receipt access control lives in the page (server component), not an API route.** `GET /receipts/:id` redirects non-parties to `/rooms` (307) via `requireUser()` + party check in `receipts/[receiptId]/page.tsx`. Correct, but be aware the protection is in the RSC, not a reusable API guard — keep that in mind if a JSON receipt endpoint is ever added.

## Defenses that held particularly well
- **Ownership, not existence.** Every owner-scoped route resolves the resource then compares `ownerId`/`agentId` to the caller (`userOwnsAgent`, participant lookups, `device.agentId` equality). Bogus-but-well-formed ids return 403/404, never 2xx (tests 9b–9d, 5d–5g).
- **Runner token scoping.** A device token is bound to exactly one `agentId`; cross-agent source attest, instruction-fail, history read, and message post are all rejected by id-equality checks before any mutation.
- **Auto-pay forbidden line.** `can_commit`/`can_spend` are hardcoded to `false` server-side regardless of request body (test 8i) — the MVP "no autonomous payment" invariant cannot be flipped via the API.
- **Rate limits enforced in DB, per-room (5 pending) and per-user-hour (30), returning 429** — not client-side.
- **Admin gate** is a hard `user.role !== "admin"` check; role is derived server-side from `ADMIN_EMAILS` in the JWT, not trusted from the request body (test 2/2b).

## Summary (10 lines)
1. 57 authorization/abuse assertions run across boundaries 1–9; **57 PASS, 0 FINDING**.
2. All cross-user resource access (pairing, verification, permissions, instructions, message read, room close) blocked with 403/404.
3. Admin-only verification approval blocked for normal users (403); body-based role escalation ineffective.
4. Approval/receipt flows enforce owner-only, counterpart-only, single-use, approved-only, trade-only — all correct.
5. Runner Bearer tokens are agent-scoped; cross-agent post/attest/fail/history-read all rejected; pairing codes are single-use.
6. Trade gate blocks rooms without `can_negotiate`, and the gate runs before room-reuse so revocation can't be bypassed.
7. Rate limits (5 pending/room, 30/hour/user) and input validation (size, type, missing fields, malformed JSON, handle regex) all enforced server-side.
8. `can_commit`/`can_spend` cannot be enabled via the API — auto-pay forbidden line holds.
9. Top 3 residual risks (all low/informational): (a) trade gate ignores the target's `can_negotiate`; (b) user-controlled text flows into the future LLM prompt context (prompt-injection surface); (c) receipt access control is enforced in the RSC rather than a reusable API guard.
10. Overall posture for this surface is strong — no exploitable authZ leak found.
