# OpenCanal — Personal-Agent Happy-Path QA Report (Round 2)

**Date:** 2026-06-14
**Tester:** QA (API-level, simulated runner) — read + test only, no source modified
**Environment:** Next.js API `http://localhost:3000`, WS gateway `http://localhost:8787`, Postgres up
**Method:** Node.js `fetch` with per-user cookie jars (`redirect:"manual"`, `getSetCookie()`), dev `dev-email` login. Two fresh normal users with unique emails (`t2-journey-{a,b}-<rand>@test.com`) to dodge the 30/hr/user instruction cap. Tester acted as each agent's runner via `/api/runner/*` with device tokens from pairing. Temp harness lived under `tmp-journey2/` and was deleted.

**Headline result:** The entire personal-agent happy path works end to end and cleanly — login → create agent (both source kinds) → pair runner → attest opencrab source (pending→linked) → discover counterpart via directory → open question room → instruct own agent → runner drains + posts → counterpart runner receives → auto-reply → originator sees reply. The **discovery gap flagged in the 2026-06-12 report (round 1) is now CLOSED** by the new `GET /api/agents/directory` endpoint, which returns other users' agents with the `id` needed to open a room and supports `?q=` search. Product invariants hold: owners cannot message the counterpart directly (405), instructions are private to the owner and flip to `processed`, and idempotency/cross-agent guards return correct 409/404.

No blocking bugs. Two minor issues: (1) the 405 on the dead direct-message route omits the RFC-required `Allow` header; (2) directory does not expose source link status, so confirming pending→linked is only possible via the runner inbox or the server-rendered profile page, not a public JSON endpoint.

---

## Step-by-step results

| # | Step | Method / Path | Rating | Status / Notes |
|---|------|---------------|--------|----------------|
| AUTH | Two users login | `GET /api/auth/csrf` → `POST /api/auth/callback/dev-email` (form) → `GET /api/auth/session` | works cleanly | callback `302`, session returns `{id,email,role:"user"}`. Email is lowercased server-side. |
| 1 | Create agent A (`manual_profile` + tastes/hobbies/skills) | `POST /api/agents` | works cleanly | `201 {id,handle}`; manual source auto-created `status:"linked"`. |
| 1 | Create agent B (`opencrab_pack` + packId) | `POST /api/agents` | works cleanly | `201`; opencrab source created `status:"pending"`. Both agents born **L1** (email login = verified). |
| 2 | Pair runner A | `POST /api/agents/:id/pairing` → `POST /api/runner/pair` | works cleanly | pairing `201 {code,expiresAt}`; pair `200 {deviceToken:"ocd_…",agentId,handle,displayName}`. Token plaintext returned only here. |
| 2 | Pair runner B | same | works cleanly | same shape. |
| 2 | Attest opencrab source | `GET /api/runner/inbox` → `POST /api/runner/sources/:sid/attest` | works cleanly | inbox lists source `status:"pending"`; attest `200 {ok:true,status:"linked"}`; re-fetched inbox shows `status:"linked"` with merged config (`manifestHash`, `nodeCount`, `spaces`, `attestedAt`). |
| 2 | Confirm flip is observable | `GET /api/runner/inbox` (post-attest) | works cleanly | Flip confirmed via inbox `sources[].status`. **Directory does NOT surface source status** — see Issue 2. |
| 5 | Discovery — directory returns others' agents w/ id | `GET /api/agents/directory` | works cleanly | `200`, returns A and B (and 48 others), each with `{id,handle,displayName,type,status,verificationLevel,bio}`. The `id` is exactly what `POST /api/rooms` needs. Round-1 blocker is resolved. |
| 5 | Discovery — search by q | `GET /api/agents/directory?q=journey` and `?q=<handle-prefix>` | works cleanly | `q=journey` → 2 hits (matches displayName, case-insensitive); handle-prefix → 1 hit. Bad `type` enum values are whitelisted server-side (no 500). |
| 3 | A opens question room to B | `POST /api/rooms {type:"question",targetAgentId:B,initiatorAgentId:A}` | works cleanly | `201 {roomId}`. Self-room and non-owned initiator correctly rejected by code (403/400 guards present). |
| 3 | A instructs own agent | `POST /api/rooms/:id/instructions {content}` | works cleanly | `201 {instructionId}`. |
| 3 | A's runner drains instruction | `GET /api/runner/inbox` (Bearer A) | works cleanly | Instruction present with resolved `counterpart:{agentId,handle,agentType,verificationLevel}` for B. |
| 3 | A's runner posts agent message | `POST /api/runner/messages {roomId,instructionId,content,needsApproval:false}` | works cleanly | `201 {messageId,requiresApproval:false}`. |
| 3 | B's runner receives the message | `GET /api/runner/inbox` (Bearer B) | works cleanly | A's message appears as pending `room.message` with sender metadata. |
| 3 | B's runner auto-replies | `POST /api/runner/messages {roomId,inReplyToId,content}` | works cleanly | `201 {messageId}`. The replied-to message is atomically marked `answered` (drops out of B's inbox on next drain). |
| 3 | A sees the reply | `GET /api/rooms/:id/messages` (A) | works cleanly | Reply present in thread (2 messages total). Also reappears in A's runner inbox as a new pending incoming message — correct for a multi-turn loop. |
| 4 | Instruction marked processed | `GET /api/rooms/:id/messages` (A) | works cleanly | Instruction `status:"processed"` with `resultMessageId` linking to A's agent message. |
| 4 | Instructions private to owner only | `GET /api/rooms/:id/messages` (A vs B) | works cleanly | A sees 1 instruction; **B sees 0 instructions** while still seeing A's agent message. Private side-channel holds. |
| 4 | Direct message POST blocked | `POST /api/rooms/:id/messages` | works (minor) | `405 Method Not Allowed` (route only exports GET). See Issue 1 re: missing `Allow` header. |
| edge | Re-fulfill processed instruction | `POST /api/runner/messages` (same instructionId) | works cleanly | `409 {error:"already processed …"}` — idempotent claim via `updateMany(status:pending)`. |
| edge | Cross-agent attest | `POST /api/runner/sources/:B-source/attest` (Bearer A) | works cleanly | `404 {error:"source not found"}` — ownership enforced. |
| infra | Gateway push leg | `POST :8787/internal/notify` | works cleanly | `200 {delivered:false,reason:"runner offline — queued in DB"}`. Push is fire-and-forget; DB-pending + inbox-drain is the resilient delivery path and works regardless of gateway/WS state. |

---

## Bugs / issues

### Issue 1 — 405 on dead direct-message route omits `Allow` header (minor, HTTP correctness)
- **Repro:** `POST http://localhost:3000/api/rooms/<roomId>/messages` with `{"content":"x"}` (authenticated).
- **Actual:** `405 Method Not Allowed`, empty body, **no `Allow` response header** (raw headers: `vary`, `Date`, `Connection`, `Keep-Alive`, `Transfer-Encoding` only).
- **Expected:** RFC 7231 §6.5.5 requires a `405` to include `Allow: GET`. Clients/proxies that introspect allowed methods get nothing. This is Next.js default behavior for a route file that exports only `GET` (no custom handler needed — the product rule is correctly enforced), so it is cosmetic, not a security gap.
- **Severity:** low.

### Issue 2 — directory cannot confirm source link status (minor, observability/UX)
- **Repro:** `GET /api/agents/directory?q=<handle>` after attesting an opencrab source.
- **Actual:** directory entry returns `{id,handle,displayName,type,status,verificationLevel,bio}` — `status` here is the agent's presence (`offline`/`online`), **not** the source link state. There is no JSON endpoint exposing `source.status`.
- **Expected (for a QA/owner):** some API way to confirm pending→linked. Currently only observable via (a) the owning agent's runner inbox `sources[].status`, or (b) the server-rendered profile page `/agents/[handle]` (which does render `linked`/`pending`). A counterpart browsing the directory has no signal that an agent's knowledge source is actually attested.
- **Severity:** low (by design — source attestation detail is arguably owner-private; flag only if "verified knowledge" should influence discovery ranking/trust badges).

---

## UX / friction notes
- **Presence vs. delivery is decoupled and robust.** Runners that only HTTP-poll the inbox (no live WS) still receive everything; the gateway returning `delivered:false` is expected and harmless. Good resilience design.
- **Counterpart resolution is pre-baked into the inbox.** The runner gets `counterpart` on instructions and full sender metadata on messages, so a runner needs no extra round-trips to know who it's talking to. Nice.
- **`needsApproval` and `room.type:"trade"` both force approval** (`approval:"required"`); question-room happy path with `needsApproval:false` posts immediately. Not exercised here beyond confirming the question path is friction-free.
- **Idempotency is solid.** Instruction fulfillment and reply-claiming both use atomic `updateMany(where status:pending)` inside a transaction; concurrent WS-push + inbox-drain cannot double-post.
- **Handle uniqueness** returns a friendly `409` (Korean message) and survives a create race via `P2002` → `409` mapping.
- Minor: directory returns up to 50 agents with no pagination cursor; fine for MVP, will need paging as the population grows.

---

## Verdict
Personal-agent happy path: **PASS, clean.** All 5 scoped steps work as specified, the round-1 discovery blocker is resolved, and the product's core invariant (owners instruct their own agent; only the runner posts) is correctly enforced with a proper 405 on the direct path. Only two low-severity polish items (missing `Allow` header; no public source-link-status signal).
