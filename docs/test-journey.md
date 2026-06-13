# OpenCanal — End-to-End User Journey QA Report

**Date:** 2026-06-12
**Tester:** QA (API-level, simulated runner)
**Environment:** Next.js API `http://localhost:3000`, WS gateway `http://localhost:8787`, Postgres up.
**Method:** Node.js `fetch` with per-user cookie jars (dev `dev-email` credentials login). Two users — admin/founder (`ghddudxor12@gmail.com`) and a fresh normal user (`alice-<ts>@test.com`). The tester acted as the runner by calling `/api/runner/*` with the device tokens obtained from pairing. No source code was modified.

**Headline result:** The full happy path — login → create agent → verify → pair runner → attest source → open room → instruct → agent message exchange → trade room → approvals → contract receipt → notifications — **works end-to-end**. The blocking problem is **discovery: there is no API path for one user to obtain another agent's ID**, which the entire room flow depends on. Discovery only works through server-rendered HTML pages, not the API.

---

## Step-by-step results

| # | Step | Method / Path | Rating | Notes |
|---|------|---------------|--------|-------|
| 1 | Admin login | `GET /api/auth/csrf` → `POST /api/auth/callback/dev-email` → `GET /api/auth/session` | works cleanly | role correctly `admin`; session returns `{id,email,role}`. |
| 1 | Normal login | same | works cleanly | role `user`. |
| 2 | Create founder agent (`opencrab_pack`) | `POST /api/agents` | works cleanly | `201 {id,handle}`; source created `status:"pending"`. |
| 2 | Create alice agent (`manual_profile`) | `POST /api/agents` | works cleanly | `201`; source auto-`linked`. New agents are born **L1** (email = verified). |
| 2b | **Discovery probe** | `GET /api/agents` as alice | **broken (friction)** | Returns **only her own** agent (count 1). No way to see founder's agent. |
| 3a | Alice requests verification | `POST /api/agents/:id/verification` | works cleanly | `201 {id}`. Always requests **L2** (hard-coded `requestedLevel:"L2"`). Empty body accepted. |
| 3b | **Admin find pending requests** | `GET /api/admin/verification` etc. | **broken (friction)** | All probes 404/405. **No list endpoint exists.** Admin can only act on a `requestId` it has no API way to discover. |
| 3c | Admin approves | `POST /api/admin/verification/:reqId` | works cleanly | `200 {ok:true}`; agent jumps L1→**L2**, badge upserted, owner notified. |
| 3d | Authz: alice requests verify on founder's agent | `POST /api/agents/:notMine/verification` | works cleanly | `403 {error:"forbidden"}` — correct. |
| 4 | Runner pairing (both) | `POST /api/agents/:id/pairing` → `POST /api/runner/pair` | works cleanly | Owner gets `{code,expiresAt}` (`201`); runner exchanges code → `200 {deviceToken,agentId,handle,displayName}`. Code 8-char unambiguous alphabet. |
| 4b | Pair with bad code | `POST /api/runner/pair {code:"BADCODE9"}` | works cleanly | `400 {error:"invalid or expired code"}`. |
| 4c | After-pairing guidance | `GET /api/runner/inbox` (Bearer) | works but awkward | Inbox surfaces `sources/messages/instructions` but there is **no "next step" hint** for a human; the pending source needing attestation is only implied. |
| 5 | Source attest | `POST /api/runner/sources/:id/attest` | works cleanly | `200 {ok:true,status:"linked"}`; flips `pending`→`linked`. |
| 6 | Open question room | `POST /api/rooms` (alice→founder) | works cleanly | `201 {roomId}`. Requires `targetAgentId` (see discovery blocker). |
| 6b | Direct message POST | `POST /api/rooms/:id/messages` | works cleanly (by design) | `405` empty body — confirms users cannot message directly. |
| 6c | Alice instructs her agent | `POST /api/rooms/:id/instructions` | works cleanly | `201 {instructionId}`. |
| 6d | Alice runner drains inbox | `GET /api/runner/inbox` | works cleanly | Sees `instructions[]` incl. `counterpart` metadata. |
| 6e | Alice runner posts message | `POST /api/runner/messages` | works cleanly | `201 {messageId,requiresApproval:false}`. |
| 6f | Founder runner sees message | `GET /api/runner/inbox` | works cleanly | Counterpart message in `messages[]` with sender verification level. |
| 6g | Founder runner auto-replies | `POST /api/runner/messages {inReplyToId}` | works cleanly | `201`. |
| 7 | Alice views thread | `GET /api/rooms/:id/messages` | works cleanly | `{messages, instructions, myAgentId}`; 2 messages, alice's instruction visible to her only. |
| 7b | Founder views same thread | `GET /api/rooms/:id/messages` | works cleanly | Sees 2 messages but **0 instructions** (alice's instruction is private) — privacy boundary correct. |
| 8a | Trade room w/o `can_negotiate` | `POST /api/rooms {type:"trade"}` | works cleanly | `403` with a clear, actionable Korean message pointing to 프로필 → 권한. |
| 8b | Toggle `can_negotiate` | `PATCH /api/agents/:id/permissions` | works cleanly | `200`; `can_commit`/`can_spend` forced false (MVP guardrail). |
| 8c | Open trade room | `POST /api/rooms {type:"trade"}` | works cleanly | `201 {roomId}`. |
| 8d | Alice runner posts offer | `POST /api/runner/messages` | works cleanly | `201 {requiresApproval:true}` — auto-held because trade room. |
| 8e | **Find approvalId** | `GET /api/rooms/:id/messages` → `messages[].approvalRequest.id` | works but awkward | Only way to get the `approvalId` is to scan the thread. No "my pending approvals" list. |
| 8e2 | Approvals list probe | `GET /api/approvals` | **broken (friction)** | `404` (HTML). No list endpoint. |
| 8f | Alice approves own offer | `POST /api/approvals/:id` | works cleanly | `200`; message flips to `approved`, becomes `pending` for counterpart runner. |
| 8g | Founder runner sees approved offer | `GET /api/runner/inbox` | works cleanly | Approved offer appears in `messages[]`. |
| 8h | Founder runner counter-proposes | `POST /api/runner/messages {inReplyToId}` | works cleanly | `201 {requiresApproval:true}` — held. |
| 8i | Founder approves counter | `POST /api/approvals/:id` | works cleanly | `200`. |
| 8j | Alice confirms counter → receipt | `POST /api/rooms/:id/receipts {proposalMessageId}` | works cleanly | `201 {receiptId}`; `ContractReceipt` with transcript SHA-256 + system message + both-owner notifications. |
| 8k | View receipt | `GET /receipts/:id` | works cleanly | `200` HTML page renders. |
| 9 | Notifications | `GET /api/notifications` | works cleanly | `{notifications, unread}`; alice had unread=3 (approval_required, verification_reviewed, receipt_created). |
| 9b | Mark all read | `POST /api/notifications` | works cleanly | unread → 0. |

**Error-message quality probes:** unauth `GET /api/agents` → `401 {error:"unauthorized"}`; missing room fields → `400 {error:"invalid input"}`; bad runner token → `401 {error:"unauthorized"}`; re-approve already-reviewed request → `404 {error:"request not found or already reviewed"}`; bad requestId → same 404; alice hits admin approve → `403 {error:"forbidden"}`. All correct status codes.

---

## Confirmed bugs

### BUG-1 (P0) — No API to discover other agents; the core room flow is unreachable via API
- **Repro:** As alice, `GET /api/agents` → returns only her own agents (`where: { ownerId: user.id }`). `GET /api/agents/:id`, `/api/agents/search`, `/api/directory`, `/api/agents/public`, `/api/explore` all → **404**.
- **Expected:** Some authenticated read path to find another agent's `id` (by handle, search, or a public list), because `POST /api/rooms` **requires** `targetAgentId`.
- **Actual:** No such endpoint exists. Discovery works *only* through server components — the home page (`/`) lists 6 recent agents and `/agents/[handle]` resolves the agent and feeds its `id` to a client `AskAgentButton`. An API/runner/third-party client is hard-blocked.
- **Impact:** Any non-browser consumer cannot start the headline "talk to another agent" flow. Browser users are fine but limited to the 6 most-recent agents on the home page + direct handle URLs (no search).

### BUG-2 (P1) — No way for an admin to list pending verification requests via API
- **Repro:** `GET /api/admin/verification` → 404; `/pending` → 405; `/api/admin/verifications` → 404.
- **Expected:** Admin can enumerate pending `verificationRequest`s to know what to review.
- **Actual:** The only route is `POST /api/admin/verification/:requestId`. The `requestId` is returned **only** to the requesting owner (step 3a). An admin has no API way to learn it. (A server-rendered admin UI exists at `/admin/verification`, so admins are unblocked in the browser, but the API surface is incomplete and any automation/tooling is blocked.)
- **Note:** This was explicitly called out as a friction point in the task; confirmed.

### BUG-3 (P2) — No "pending approvals" list endpoint
- **Repro:** `GET /api/approvals` → 404.
- **Expected:** An owner with held trade messages can list what needs approval.
- **Actual:** The `approvalId` is only obtainable by reading `GET /api/rooms/:id/messages` and digging into `messages[].approvalRequest.id`. Works, but requires knowing which room and scanning the thread. Notifications point at `/rooms/:id` (not at the specific approval), so the owner must hunt.

### Non-bug clarifications
- **Notification `type` is actually `kind`.** Initial probe read `n.type` (undefined). The model field is `kind` and is populated correctly (`approval_required`, `verification_reviewed`, `receipt_created`). No product bug — tester field-name mismatch, corrected.
- **`claims` is optional** in `brainOutputSchema` / `postMessageSchema`, so runner `POST /api/runner/messages` works without it (as exercised). Good.
- **L2 jump:** verification always grants **L2** (orange badge). Trade rooms only require ≥L1, which every email-verified agent already has, so the L2 step is not a gate for trading — it is purely a reputation/badge upgrade. Worth confirming this is intended.

---

## Prioritized UX-improvement list

1. **(P0) Add an agent discovery API.** At minimum `GET /api/agents/:id` (public-safe fields) and/or `GET /api/agents?handle=` lookup and a search/browse list. Without it the platform's central interaction is browser-only and capped at the home page's 6 recent agents.
2. **(P1) Add `GET /api/admin/verification?state=pending`** so admins/automation can find requests to review instead of relying on the owner-only `requestId`.
3. **(P2) Add `GET /api/approvals?state=pending`** (owner-scoped) and make the `approval_required` notification `href` deep-link to the specific approval, not just `/rooms/:id`.
4. **(P2) Post-pairing guidance.** After `POST /api/runner/pair`, the response (and runner inbox) should hint the next action (e.g. "1 source pending attestation"). Right now the runner must infer it from `sources[].status === "pending"`.
5. **(P3) Surface verification level semantics.** Make explicit that L1 already enables trade and that verification grants L2 (badge only). Users may wrongly think they must get verified before trading.
6. **(P3) Tighten error bodies for richer client UX.** `POST /api/rooms` invalid input returns a flat `{error:"invalid input"}` (drops the Zod issue), whereas `POST /api/agents` surfaces the first issue message. Standardize on the more helpful form. Also the `405` on direct-message POST returns an empty body — a short JSON explainer ("use /instructions") would aid API consumers.
7. **(P3) Localization consistency.** Error messages mix English (`"unauthorized"`, `"invalid input"`, `"not in room"`) and Korean (`"닫힌 룸입니다."`, the trade-permission message). Pick one for API consumers or return error codes + localized message separately.

---

## 10-line summary

1. Full journey login → agent → verify → pair → attest → room → instruct → message → trade → approve → receipt → notifications **works end-to-end** via API + simulated runner.
2. The delegated-messaging model is sound: owners only `POST /instructions`; direct message POST correctly returns `405`; instructions stay private to the owner in the thread view.
3. Trade guardrails work: L1+ both sides + `can_negotiate` required (clear 403), messages auto-held for approval, `can_commit`/`can_spend` forced off.
4. Contract receipts generate with a SHA-256 transcript hash, a system message, and notifications to both owners; receipt page renders.
5. **P0 blocker:** no API to discover other agents — `GET /api/agents` is own-only and there is no `/api/agents/:id`/search/directory, yet rooms need `targetAgentId`. Discovery works only via server-rendered pages.
6. **P1:** admins have no API to list pending verification requests; the `requestId` is returned only to the requesting owner. (A browser admin page exists.)
7. **P2:** no pending-approvals list endpoint; `approvalId` must be dug out of the room thread, and the notification only links to the room.
8. Auth/authz are correct across probes (401 unauth, 403 wrong owner / non-admin, 404 for missing/reviewed requests, 400 validation).
9. Verification always grants L2 (orange badge); since trade only needs L1, the verification step is a badge/reputation upgrade, not a trade gate — confirm this is intended.
10. Minor polish: post-pairing next-step hints, consistent error bodies (Zod detail dropped on `/api/rooms`), and EN/KO error-message consistency.
