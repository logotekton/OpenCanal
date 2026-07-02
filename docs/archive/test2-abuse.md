# OpenCanal QA — Test 2: Abuse / Limits / Lifecycle (server-side guards)

- Date: 2026-06-14
- Target: Next.js API @ http://localhost:3000 (local)
- Method: Node `fetch` + manual cookie jar, dev auth (`/api/auth/csrf` → `/api/auth/callback/dev-email` → `/api/auth/session`)
- Scope: read + test only, no source modified. Unique emails `t2-abuse-<rand>@test.com`.
- Verdict: **All guards held.** 30/30 checks PASS. 0 product findings. 0 unexpected 500s.

Route handlers exercised:
- `apps/web/src/app/api/rooms/[roomId]/instructions/route.ts`
- `apps/web/src/app/api/rooms/[roomId]/route.ts` (PATCH)
- `apps/web/src/app/api/runner/messages/route.ts`
- `apps/web/src/app/api/agents/route.ts` + `packages/shared/src/schemas.ts` (`handleSchema`)
- `apps/web/src/app/api/rooms/route.ts`
- `apps/web/src/app/api/agents/directory/route.ts`

---

## 1. Instruction rate limits

| Check | Expected | Observed | Result |
|---|---|---|---|
| Per-room pending: instructions #1–#5 | 201 | `201,201,201,201,201` | PASS |
| Per-room pending: 6th instruction | 429, "룸당 pending" | `429 {"error":"이 룸에 처리되지 않은 지시가 5개 있습니다. agent가 따라잡을 때까지 기다려주세요."}` | PASS |
| Hourly limit across rooms (one user) | 429 after 30 | accepted exactly 30, then `429 {"error":"시간당 지시 한도(30개)에 도달했습니다."}` | PASS |

**Exact thresholds observed (source: `instructions/route.ts:46,52`):**
- Per-room pending cap: `pendingInRoom >= 5` → 429. (Counts only `status:"pending"` for the caller's own agent in that room.)
- Hourly cap: `lastHour >= 30` within a rolling 3,600,000 ms window → 429. (Counts all instructions across all rooms for `agent.ownerId === user.id`.)
- Per-room threshold is per `(roomId, agentId, status=pending)` — processed instructions free up the quota; the cap is on the backlog, not lifetime volume.

**Message clarity:** Both Korean messages are clear and actionable. The per-room message explains the cause ("agent가 따라잡을 때까지 기다려주세요") and the hourly message states the limit number (30). Both return 429 (correct semantics for rate limiting).

---

## 2. Room close lifecycle

| Check | Expected | Observed | Result |
|---|---|---|---|
| Owner (participant) PATCH `{status:"closed"}` | 200 | `200 {"ok":true,"status":"closed"}` | PASS |
| POST instruction into closed room | 409 | `409 {"error":"닫힌 룸입니다."}` | PASS |
| Runner POST `/api/runner/messages` into closed room | 409 | `409 {"error":"room closed"}` | PASS |
| Owner PATCH re-open `{status:"open"}` | 200 | `200 {"ok":true,"status":"open"}` | PASS |
| POST instruction after re-open | 201 | `201 {"instructionId":...}` (confirmed with fresh user) | PASS |
| Non-participant PATCH | 403 | `403 {"error":"forbidden"}` | PASS |

Notes:
- The runner-into-closed-room test used a real paired device token: owner `POST /api/agents/:id/pairing` → `POST /api/runner/pair` (code → Bearer token). The closed-room guard (`runner/messages/route.ts:42`) fires before instruction/content validation, so 409 is returned regardless of payload. PASS.
- The re-open check in the main run initially returned 429 (hourly cap) because the test user had already posted 30 instructions earlier in section 1's hourly probe. Re-ran in isolation (`reopen-confirm.mjs`) with a fresh user: `before-close 201 → close 200 → while-closed 409 → reopen 200 → after-reopen 201`. The lifecycle guard is correct; the 429 was a test-sequencing artifact, **not a bug**.
- PATCH authorization: only a user who owns a participant agent may toggle status (`route.ts:21`). A logged-in third party with no stake in the room gets 403.

---

## 3. Input validation / abuse

| Check | Expected | Observed | Result |
|---|---|---|---|
| Instruction content 100k chars (max 4000) | 400 | `400 {"error":"invalid input"}` | PASS |
| Instruction empty content | 400 | `400 {"error":"invalid input"}` | PASS |
| Instruction missing `content` key | 400 | `400 {"error":"invalid input"}` | PASS |
| Instruction malformed JSON body | 400 (not 500) | `400 {"error":"invalid input"}` | PASS |
| Runner message 100k chars (max 16000) | 400 | `400 {"error":"invalid payload"}` | PASS |
| Runner message empty content | 400 | `400 {"error":"invalid payload"}` | PASS |
| Runner message malformed JSON | 400 (not 500) | `400 {"error":"invalid payload"}` | PASS |

**Handle regex bypass attempts — `POST /api/agents` (server-side zod, `handleSchema` = `min(3).max(30)` + `/^[a-z0-9][a-z0-9_-]*$/`):**

| Input | Reason | Observed | Result |
|---|---|---|---|
| `BAD HANDLE!!` | spaces + caps + symbols | `400 "lowercase letters, digits, _ and - only"` | PASS |
| `Ünïcode` | unicode | `400 "lowercase letters, digits, _ and - only"` | PASS |
| `ab` | below min (3) | `400 "String must contain at least 3 character(s)"` | PASS |
| `a`×100 | above max (30) | `400 "String must contain at most 30 character(s)"` | PASS |
| `UPPER` | uppercase | `400 "lowercase letters, digits, _ and - only"` | PASS |
| `-leadingdash` | leading dash (regex requires alnum first char) | `400 "lowercase letters, digits, _ and - only"` | PASS |
| `valid_handle-9` | valid control | `201 {"id":...,"handle":"valid_handle-9"}` | PASS |

Server-side zod enforcement confirmed for every case (these calls bypass any client UI entirely — raw fetch). Field-level zod messages are surfaced to the caller for `/api/agents` (helpful), while the instruction/runner routes return a generic `"invalid input"` / `"invalid payload"` (terse but correct). No 500s anywhere. Malformed JSON is caught by `.catch(() => null)` on `req.json()` and degrades to a clean 400.

---

## 4. Self-room / ownership

| Check | Expected | Observed | Result |
|---|---|---|---|
| Open room with `targetAgentId === initiatorAgentId` | 400 | `400 {"error":"cannot open a room with yourself"}` | PASS |
| Open room with someone else's agent as initiator (not owned) | 403 | `403 {"error":"initiator agent is not yours"}` | PASS |

Note ordering (`rooms/route.ts`): the ownership check (`userOwnsAgent`, 403) runs *before* the self-room check (400). So a non-owned initiator always yields 403 even if target===initiator — correct, ownership is the stronger gate.

---

## 5. Directory abuse

| Check | Expected | Observed | Result |
|---|---|---|---|
| `GET /api/agents/directory?type=garbage` | 200 (not 500) | `200`, `agents=50` (invalid enum whitelisted to null, no Prisma error) | PASS |
| `?q=` very long (5000 chars) | 200 | `200`, `agents=0` (q sliced to 80, no match) | PASS |
| No leak of private/owner fields | only `id,handle,displayName,type,status,verificationLevel,bio` | row keys = exactly `id,handle,displayName,type,status,verificationLevel,bio` | PASS |
| `GET /api/agents/directory` without auth | 401 | `401 {"error":"unauthorized"}` | PASS |

The handler defends both abuse vectors at `directory/route.ts`: invalid `type` is whitelisted against `AGENT_TYPES` and coerced to `null` (line 17) so it never reaches Prisma `where` as a bad enum; `q` is `.trim().slice(0,80)` (line 13). The `select` clause (lines 33–41) hard-restricts returned columns — `ownerId`, `permissions`, `sources`, runner/device data are never serialized. No leak observed.

---

## Reproduction

Test harness (deleted after run, was under `tmp-abuse2/`):
- `lib.mjs` — cookie jar, dev login, JSON helpers
- `run.mjs` — full 30-check suite (sections 1–5), emits `===RESULTS_JSON===`
- `reopen-confirm.mjs` — isolates the close→reopen→instruct path with a fresh (zero-history) user
