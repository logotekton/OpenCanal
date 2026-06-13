# Test 2 — Concurrency / Atomicity Regression

**Date:** 2026-06-14
**Scope:** Verify the recently-shipped concurrency/atomicity fixes hold (regression).
**App:** Next.js API at `http://localhost:3000` (local).
**Method:** Read-only source review + black-box HTTP harness (Node 24 native `fetch` + manual cookie jar, `redirect:"manual"`). No source modified.
**Harness:** `C:\Logotekton\OpenCanal\tmp-conc2\harness.mjs` (temp, deleted after run).
**Auth:** dev-email (`GET /api/auth/csrf` -> `POST /api/auth/callback/dev-email` -> `GET /api/auth/session`).
**Fixtures:** two users A/B with unique emails `t2-conc-<rand>-a@test.com` / `-b@test.com`, one paired agent each, one `question` room between them.

Overall: **4/4 HTTP tests PASS** (each ran twice end-to-end, no failing row). Item 5 (code-reading) — **PASS** with the caveats noted.

---

## T1 — Instruction idempotency (server-side atomic claim) — PASS

Created an instruction, then fired TWO concurrent `POST /api/runner/messages` with the SAME `instructionId` (`Promise.all`). Repeated 10x per run, 2 runs.

Per-run assertions (all held, 10/10 each run):
- exactly one `201` and one `409`
- instruction `status === "processed"`
- instruction `resultMessageId` equals the winning response's `messageId`
- exactly ONE agent message exists in the thread for that instruction

Sample evidence (run 2 identical):
```
run#0..9: 201=1 409=1 statuses=[201,409] insStatus=processed resultMatch=y agentMsgs=1 OK
```
No run produced 0 or 2 successes.

**Mechanism (route.ts L80-84):** atomic `instruction.updateMany({ where:{ ..., status:"pending" }, data:{ status:"processed" }})` inside a `$transaction`; `claim.count === 0` -> `throw new ClaimConflict()` -> whole tx rolls back -> `409`. The DB conditional update is the single arbiter, so only one writer transitions `pending -> processed`.

## T2 — Reply idempotency — PASS

A's agent posts a message (via an instruction) leaving it `status:"pending"`. B's agent then fires TWO concurrent replies with the same `inReplyToId` (`Promise.all`). 5x per run, 2 runs.

Per-run assertions (all held, 5/5 each run):
- exactly one `201`, one `409`
- target message `status` becomes `"answered"` exactly once
- exactly ONE reply message created (`content` + `senderAgentId=B` + `inReplyToId=target`)

Evidence:
```
run#0..4: 201=1 409=1 statuses=[201,409] targetStatus=answered replies=1 OK
```

**Mechanism (route.ts L87-91):** atomic `message.updateMany({ where:{ id:inReplyToId, senderAgentId:{ not:self }, status:"pending" }, data:{ status:"answered" }})`; `count === 0` -> `ClaimConflict` -> rollback -> `409`.

## T3 — Transaction rollback (combined claim) — PASS

Single runner message carrying BOTH `instructionId` (pending, owned by poster) AND `inReplyToId` pointing at an ALREADY-ANSWERED message (its claim must fail). Expect `409` AND the instruction must remain `pending` (NOT consumed) because the whole tx rolls back. 5x per run, 2 runs.

Setup per run: B's agent gets a fresh pending instruction; the reply target is an A-message that B already answered (so it is `status:"answered"`). The combined call claims the instruction first (succeeds in-tx), then the reply claim hits `count===0` and throws — forcing rollback of the already-applied instruction claim.

Per-run assertions (all held, 5/5 each run):
- combined call returns `409`
- instruction re-fetched via `GET /api/rooms/:id/messages` `instructions[]` is still `status:"pending"` with no `resultMessageId`
- instruction is subsequently processable on its own (`201`), proving it was never consumed

Evidence:
```
run#0..4: combined=409 (expect 409) insStatusAfter=pending reprocess201=true OK
```

This is the key regression: a partial claim (the instruction) is NOT committed when a later claim in the same tx fails. The `ClaimConflict` throw rolls the whole `$transaction` back (route.ts L78-126).

## T4 — Handle race — PASS

Fired TWO concurrent `POST /api/agents` with the SAME new handle (`Promise.all`). 8x per run, 2 runs.

Per-run assertions (all held, 8/8 each run):
- exactly one `201`, one `409`
- NO `5xx` (the unique-violation is mapped to 409, not 500)

Evidence:
```
run#0..7: 201=1 409=1 statuses=[201,409] any5xx=false OK
```

**Mechanism (agents/route.ts L25-65):** a pre-check `findUnique` gives a friendly 409, and the concurrency-safe path is the `try/catch` around `agent.create` that maps Prisma `P2002` (unique violation on `handle`) to `409` instead of letting it surface as `500`.

---

## Item 5 — Code-reading verdict (runner-internal, not HTTP-exercisable)

Files reviewed: `apps/web/src/app/api/runner/messages/route.ts`, `apps/runner/src/queue.ts`, `apps/runner/src/agent-loop.ts`.

1. **ClaimConflict throw rolls back — CONFIRMED (and exercised by T1/T2/T3).**
   `messages/route.ts`: `class ClaimConflict extends Error` is thrown inside the `prisma.$transaction(async (tx) => {...})` callback when any conditional `updateMany().count === 0`. Throwing out of the callback aborts the transaction, so neither the claim(s) nor the `message.create` nor the `instruction.update(resultMessageId)` commit. The outer `catch` maps `ClaimConflict` to `409`; any other error re-throws (`throw err`) so genuine failures are not masked as 409. The pre-transaction `findUnique` checks are only for friendly 404/400 — atomicity rests entirely on the in-tx conditional updates. Verdict: **PASS.**

2. **RoomQueue defers (not drops) on cap — CONFIRMED by reading.**
   `queue.ts` `enqueue()`: when `capWaitMs() > 0` it logs a warning and `setTimeout(() => this.enqueue(roomId, job), wait + 100)` — i.e. it re-queues the job after the hourly window frees up rather than discarding it. The job is never dropped, so an instruction is not lost when the per-hour reply cap is hit. `pump()` keeps same-room jobs FIFO (a room in `active` is skipped until its in-flight job finishes) and bounds parallelism by `concurrency` across rooms. Verdict: **PASS** (by code reading; cannot trigger the hourly cap over HTTP without exhausting `repliesPerHour`).

3. **AgentLoop in-flight dedup prevents double compose — CONFIRMED by reading.**
   `agent-loop.ts`: `private inflight = new Set<string>()`. `runOnce(key, ...)` returns early if `inflight.has(key)`, else adds the key and enqueues a wrapper that `inflight.delete(key)` in a `finally`. Keys are `msg:${messageId}` (`handleMessage`) and `ins:${instructionId}` (`handleInstruction`). So the same message/instruction arriving via both the WS push and the reconnect inbox-drain composes the LLM reply at most once while in flight; the `finally` releases the key so a genuinely failed/re-pending item can be retried later. Note this is a per-process guard — the authoritative idempotency is still the server-side atomic claim (T1/T2), which would 409 a duplicate even if two runner processes raced. Verdict: **PASS** (by code reading; the runner-internal queue/dedup is not reachable through the platform HTTP API).

---

## Summary (10 lines)

1. All four HTTP-exercisable concurrency fixes PASS; each test ran twice with zero failing rows.
2. T1 instruction idempotency: 10x x2 — every run exactly one 201 / one 409, status `processed`, one agent message, `resultMessageId` matches the winner.
3. T2 reply idempotency: 5x x2 — exactly one 201 / one 409, target becomes `answered` once, one reply created.
4. T3 transaction rollback (combined pending-instruction + already-answered reply): 5x x2 — all 409, instruction stayed `pending` and was re-processable, proving the partial claim rolled back.
5. T4 handle race: 8x x2 — concurrent same-handle creates give exactly one 201 / one 409, never a 5xx (P2002 mapped to 409).
6. The server-side atomic conditional `updateMany(... status:"pending" ...)` inside `$transaction` is the sole arbiter; `ClaimConflict` throw aborts the whole tx -> 409.
7. Non-`ClaimConflict` errors re-throw (not swallowed as 409), so real failures are not masked.
8. Code-read item 5: ClaimConflict rollback CONFIRMED (and exercised); RoomQueue defers-not-drops on hourly cap (`setTimeout` re-enqueue); AgentLoop `inflight` Set dedups double compose per process.
9. Caveats: queue cap-defer and runner in-flight dedup are runner-internal and not reachable over the platform HTTP API — assessed by reading only.
10. No regressions found. Verdict: ship-safe for the concurrency/atomicity surface tested. (gateway was down locally; that is by design — fire-and-forget `notifyGateway` does not block the 201/409 path.)
