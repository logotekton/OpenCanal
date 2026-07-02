# QA Test 2 — Notification System ("Neural System" of the Delegate Model)

- **Date:** 2026-06-14
- **Target:** Next.js API at `http://localhost:3000` (local dev, `ALLOW_DEV_LOGIN=true`, `ADMIN_EMAILS=ghddudxor12@gmail.com`)
- **Method:** Read-only QA. No source modified. Black-box drive via `fetch` + per-actor cookie jar (dev-email auth) and runner Bearer tokens, plus white-box read of every `notifyUser` call site.
- **Actors:** `t2-notif-<rand>-a@test.com` (Owner A / Agent A), `t2-notif-<rand>-b@test.com` (Owner B / Agent B), admin `ghddudxor12@gmail.com`.
- **Harness:** `tmp-notif2/harness.mjs` (main flows), `tmp-notif2/race.mjs` (concurrency) — temp dir deleted after run.

## Source map (the 4 notification kinds)

| Kind | Trigger route | Recipient (code) | href |
|------|---------------|------------------|------|
| `approval_required` | `apps/web/src/app/api/runner/messages/route.ts:139` | `device.agent.ownerId` (sender's owner) | `/rooms/{roomId}` |
| `instruction_failed` | `apps/web/src/app/api/runner/instructions/[instructionId]/fail/route.ts:28` | `device.agent.ownerId` | `/rooms/{instruction.roomId}` |
| `verification_reviewed` | `apps/web/src/app/api/admin/verification/[requestId]/route.ts:54` | `request.agent.ownerId` | `/agents/{handle}` |
| `receipt_created` (x2) | `apps/web/src/app/api/rooms/[roomId]/receipts/route.ts:92,96` | confirmer `user.id` + `proposal.sender.ownerId` | `/receipts/{receiptId}` |

`src/lib/notify.ts` — `notifyUser` wraps `prisma.notification.create` in try/catch and only `console.error`s on failure (never throws). Read/list path: `apps/web/src/app/api/notifications/route.ts` (GET → `{notifications, unread}`, scoped to `user.id`; POST → `updateMany` sets `readAt` for that user only).

---

## Results

### 1. approval_required — PASS
Trade room (both agents L1, both `can_negotiate=true`). Owner A instructs Agent A; Runner A posts the instructed message. Trade room ⇒ `requiresApproval=true` ⇒ message held.

- `POST /api/runner/messages` → **201** `{messageId, requiresApproval:true}`
- Owner A `GET /api/notifications` → **200**, `unread:1`, notification `{kind:"approval_required", title:"@<aHandle>의 메시지가 승인을 기다립니다", href:"/rooms/<roomId>"}`
- Owner B `GET /api/notifications` → **200**, `unread:0`, `notifications:[]`

Lands for the right user (the held message's own agent-owner, i.e. the human who must approve). Counterpart Owner B correctly receives nothing. href → `/rooms/{roomId}` resolves to `app/rooms/[roomId]/page.tsx`. **PASS.**

### 2. instruction_failed — PASS (incl. 409 / no false-notify)
Owner A creates a pending instruction; Runner A fails it.

- `POST /api/runner/instructions/{id}/fail {error:"brain timeout"}` → **200** `{ok:true}`
- Owner A `GET /api/notifications` → `instruction_failed` count = **1**, `{title:"@<aHandle>이(가) 지시를 수행하지 못했습니다", href:"/rooms/<roomId>"}`

Duplicate / already-processed checks:
- Fail the SAME (now `failed`) instruction again → **409** `{error:"already processed"}`; `instruction_failed` count stays **1** (no duplicate, no false notification).
- Fail an already-`processed` instruction (the one consumed by the held message in test 1) → **409** `{error:"already processed"}`; count stays **1**.

**PASS.**

### 3. verification_reviewed — PASS
Owner A requests L2 verification for Agent A; admin approves.

- Non-admin guard: Owner B `POST /api/admin/verification/{id}` → **403** `{error:"forbidden"}` (no notification emitted).
- Admin `POST /api/admin/verification/{id} {decision:"approved", note:"looks good"}` → **200** `{ok:true}`
- Owner A `GET /api/notifications` → new `{kind:"verification_reviewed", title:"@<aHandle> 검증이 승인되었습니다 — 주황 딱지가 부여됩니다", href:"/agents/<aHandle>"}`
- Admin received **no** new notification for this action (the reviewer is not a recipient — correct).

href → `/agents/{handle}` resolves to `app/agents/[handle]/page.tsx` (uses handle, not agentId — correct). **PASS.**

### 4. receipt_created (both owners) — PASS
Owner A approves Agent A's held proposal (`POST /api/approvals/{id}` → 200), then Owner B (counterpart) confirms it.

- `POST /api/rooms/{roomId}/receipts {proposalMessageId}` → **201** `{receiptId}`
- Owner B (confirmer = `user.id`): `{kind:"receipt_created", title:"거래 합의를 확정했습니다", href:"/receipts/<receiptId>"}`
- Owner A (proposal sender's owner = counterpart): `{kind:"receipt_created", title:"@<aHandle>의 제안이 확정되었습니다", href:"/receipts/<receiptId>"}`

Both owners notified, with role-appropriate titles and the same valid receipt href. **PASS.**

### 5. Read path + cross-user isolation + href targets — PASS
- **Unread count:** `GET /api/notifications` returns accurate `unread`; grew 1→2→3→4 for Owner A across the flows.
- **Mark all read:** `POST /api/notifications` → **200** `{ok:true}`; subsequent `GET` → `unread:0` (notifications retained, `readAt` set).
- **Cross-user isolation:** Owner B's list across the whole run contained ONLY their own single `receipt_created` (the confirmer side). Owner B never saw Owner A's `approval_required`, `instruction_failed`, or `verification_reviewed`. Unauthorized `GET /api/notifications` (no cookie) → **401** `{error:"unauthorized"}`.
- **href correctness:** room kinds → `/rooms/{id}`; receipt kinds → `/receipts/{id}`; verification → `/agents/{handle}`. All three target existing page routes. No wrong/missing/duplicated href observed.

**PASS.**

### 6. Robustness — PASS (by inspection)
- `src/lib/notify.ts:15-22` — `notifyUser` swallows all errors in a try/catch (only `console.error`). A notification-write failure cannot throw into the calling route, so the main action (message post, instruction fail, verification review, receipt creation) is never broken by the notification layer. **PASS.**
- Header bell unread source: `apps/web/src/app/layout.tsx:14-16` — server component counts `prisma.notification.count({ where:{ userId: user.id, readAt: null } })`, correctly scoped to the logged-in user, badge capped at "9+". Consistent with the API `unread`. **PASS.**

---

## Findings

### FINDING-1 (Low / latent — not reproduced): `instruction_failed` fail route is not structurally race-proof
`apps/web/src/app/api/runner/instructions/[instructionId]/fail/route.ts:15-26` does a non-atomic check-then-update: `findUnique` → `if (status !== "pending") 409` → `update`. This is a TOCTOU window — unlike the sibling `runner/messages` route, which guards with an atomic `updateMany({where:{status:"pending"}})` + `claim.count===0 ⇒ rollback/409`. Two truly-simultaneous fails could both pass the `pending` check before either commits, yielding a duplicate `instruction_failed` notification.

In practice this did NOT reproduce: 5 concurrent fails on one instruction returned exactly **1×200 + 4×409**, and exactly **1** `instruction_failed` notification (`tmp-notif2/race.mjs`) — the single-row `UPDATE` serializes under Postgres' default isolation closely enough that the read-back sees the committed `failed` state. Recommend hardening to the atomic `updateMany`-claim pattern for defense-in-depth and consistency with the messages route. No user-facing impact observed.

### Non-issues confirmed
- `notifyUser` calls are `await`ed in the routes, but because the function never throws, the await is harmless (and the prior code-review note about `notifyGateway` latency does not apply to `notifyUser`).
- Reviewer/actor is never a spurious recipient (admin gets no `verification_reviewed`; the confirmer and counterpart both get `receipt_created` by design).

## Verdict
All 4 notification kinds fire, land for the correct user(s), carry correct titles and hrefs, and the read/unread/mark-all-read path and cross-user isolation all behave correctly. One low-severity latent race in the fail route (not reproduced, no impact). **Overall: PASS.**
