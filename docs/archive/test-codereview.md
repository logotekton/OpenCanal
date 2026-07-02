# OpenCanal Code Review — Correctness & Security Audit

Scope: correctness/security bugs across `apps/web` API routes, `apps/gateway`, `apps/runner`, `packages/db`, `packages/shared`. Review-only; no source modified.

---

## Spotlight verdicts (requested explicitly)

### A. Instruction double-execution TOCTOU — **BUGGY**

**Files:** `apps/web/src/app/api/runner/messages/route.ts:44-89`, `apps/runner/src/agent-loop.ts:58-64,176-186`, `apps/runner/src/ws-client.ts:18-31,42-46`

The runner can process the same instruction twice and post **two** agent messages for one instruction.

The `POST /api/runner/messages` handler does a read-then-write with no transaction and no conditional update:

```
44  if (instructionId) {
45    const instruction = await prisma.instruction.findUnique({ where: { id: instructionId } });
...
49    if (instruction.status !== "pending") { return 409; }   // CHECK
52  }
...
59  const message = await prisma.message.create({ ... });        // unconditional
...
81  if (instructionId) {
83    prisma.instruction.update({ where: { id: instructionId },  // SET (separate tx)
84      data: { status: "processed", ... } });
```

The `findUnique` status check (line 49) and the `instruction.update` (line 83) are in different awaits with no row lock and no `updateMany({ where: { status: "pending" } })` guard. Two concurrent POSTs for the same instruction both read `status==="pending"`, both pass the check, both `message.create`, and both flip the instruction to `processed`. The unique constraint that would stop this does not exist — `Instruction` has no unique key tying it to a single result message, and `Message` has no uniqueness on `inReplyToId`/instruction either.

**Concrete trigger:** This is not merely theoretical given the runner design. On WS reconnect the runner calls `drainInbox()` (`agent-loop.ts:176`) which enqueues every `status==="pending"` instruction, while a `room.instruction` push for the *same* instruction can arrive over the freshly reconnected socket (`ws-client.ts:44`). Both land in `RoomQueue` for the same room. Because they are the *same* roomId, FIFO serializes them — so they don't run truly concurrently — **but the queue does not dedupe by instructionId, so the second job still runs after the first completes.** When the second job runs, the brain composes again and calls `reply()` again; the server-side check at line 49 is the only defense, and it correctly returns 409 *if the first write already landed*. The real race window is: (1) gateway `/internal/notify` push and (2) inbox drain happening close together such that both `reply()` POSTs are in flight before either's `instruction.update` commits. With per-room FIFO this is narrow for a single runner, but: a) the queue can drop the first job silently when the hourly cap is hit (`queue.ts:30-33`) yet still run the duplicate later; b) nothing prevents two runner *processes* (e.g. user runs `start` twice, or an old process during the "replace by new connection" window) from both draining. The device-token replacement in the gateway (`index.ts:166`) closes the old *socket* but does not stop an old runner process from continuing to hit the REST API with the still-valid token.

**Fix:** Make the consume atomic and conditional:
```ts
const claimed = await prisma.instruction.updateMany({
  where: { id: instructionId, agentId: device.agentId, roomId, status: "pending" },
  data: { status: "processed", processedAt: new Date() },
});
if (claimed.count === 0) return NextResponse.json({ error: "instruction already processed" }, { status: 409 });
// then create the message and set resultMessageId
```
Wrap the claim + message create + `resultMessageId` set in a single `prisma.$transaction`. The same pattern should guard `inReplyToId` (see Finding #2) — currently a counterpart message can be auto-replied to twice.

### B. Trade / held-message visibility to counterpart — **SAFE (with one caveat)**

The core invariant holds: held messages (`approval` in `required`/`rejected`) are not leaked to the counterpart.

- `GET /api/rooms/:id/messages` (`messages/route.ts:27`): filter is `OR: [{ approval: { in: ["none","approved"] } }, { sender: { ownerId: user.id } }]`. The counterpart owner is not the sender's owner, so a `required`/`rejected` message is excluded for them. Correct.
- `GET /api/runner/inbox` (`inbox/route.ts:20-23`): `status: "pending"` AND `approval: { in: ["none","approved"] }` AND `senderAgentId != self`. A held message is `approval: "required"` so excluded; a rejected message is set to `status: "failed"` (`approvals route:43`) so excluded. Correct.
- `GET /api/runner/rooms/:id/history` (`history/route.ts:18-21`): `approval in [none,approved]` AND `status in [delivered,answered]`. Held/rejected excluded. Correct.
- Rejected messages: `approvals/[approvalId]/route.ts:43` sets `status: "failed"`, and no fanout occurs (the `notifyGateway` is inside `if (approved)`), so they never deliver. Correct.

**Caveat (low):** Approved trade messages are delivered, but `approval === "approved"` rows count as "delivered" for transcript/history purposes the moment the owner approves — there is no separate "the counterpart runner actually consumed it" state distinct from the proposer-side `pending`. This is by design per the state-machine doc, so not a bug, but note that `status` is overloaded: after approval the message is `status:"pending"` (meaning "counterpart hasn't drained") yet simultaneously visible in `GET messages`. Acceptable.

---

## High severity

### H1. `inReplyTo` auto-reply has the same TOCTOU and can double-answer
**File:** `apps/web/src/app/api/runner/messages/route.ts:76-79`

Unlike the instruction path, the `inReplyToId` path has **no guard at all** — it unconditionally `message.update({ status: "answered" })` on the parent. There is no check that the parent is still `pending`, no check that it belongs to this room/counterpart, and no idempotency. A counterpart message that is pushed (gateway) and also drained (inbox) produces **two** reply messages to the counterpart, both valid and delivered. The brain composes twice and sends two distinct replies. This directly violates the "one turn → one reply" expectation and wastes the hourly cap.

**Fix:** Guard with `updateMany({ where: { id: inReplyToId, roomId, status: "pending" } })` and bail (or skip creating the reply) when `count === 0`. Also validate `inReplyToId` belongs to `roomId` and was sent by the counterpart (currently unvalidated — a malicious/buggy runner can pass any message id, including one from another room, and mark it answered; see H2).

### H2. `inReplyToId` is not validated against the room or sender — cross-room/foreign write
**File:** `apps/web/src/app/api/runner/messages/route.ts:32-79`

`inReplyToId` is accepted from the runner and used in two ways: stored on the new message (`inReplyToId` line 65) and to flip the parent to `answered` (line 78). Neither use validates that the referenced message exists, is in `roomId`, or was authored by the counterpart. A compromised/buggy device token holder can:
- Pass an `inReplyToId` pointing at a message in **another room** → `message.update` flips an unrelated message to `answered` (the runner is authenticated only as "in `roomId`", not as related to the target message). This can hide a still-pending counterpart message in a room the attacker isn't even reasoning about, or corrupt another conversation's state.
- Set `inReplyToId` to its own prior message, distorting reply threading.

**Fix:** Look up the parent: `findUnique({ where: { id: inReplyToId } })`, require `parent.roomId === roomId` and `parent.senderAgentId !== device.agentId` (it must be the counterpart's message). 404 otherwise.

### H3. Codex adapter passes untrusted content into a shell — command injection
**File:** `apps/runner/src/brain/codex.ts:13-16`

```ts
const fullPrompt = `${systemPrompt}\n\n---\n\n${userPrompt}`;
const child = spawn("codex", ["exec", "--skip-git-repo-check", fullPrompt], { shell: true, ... });
```

With `shell: true`, the args are re-parsed by the shell. `fullPrompt` contains fully attacker-influenced data: the counterpart's message content (`agent-loop.ts:119`) and the owner instruction text both flow verbatim into the prompt, then into the constitution/userPrompt. A counterpart message such as `"; rm -rf ~ #` (or on Windows `& del ...`, backticks, `$(...)`) is interpreted by the shell, achieving arbitrary command execution on the runner's machine — the user's own laptop running their Claude/Codex subscription. This is the most dangerous finding from a security standpoint: a remote counterpart agent gains code execution on the victim's host.

**Fix:** Do not use `shell: true` with interpolated content. Pass the prompt via stdin (`child.stdin.write(fullPrompt); child.stdin.end()`) rather than as an argv element, or resolve the binary explicitly and set `shell: false`. If `.cmd` resolution on Windows is the reason for `shell: true`, resolve the full path to `codex.cmd` and invoke it directly without shell parsing.

### H4. Gateway `/internal/notify` requires no constant-time secret compare; default secret in prod path
**Files:** `apps/web/src/lib/gateway.ts:5`, `apps/gateway/src/index.ts:20,57`

Both sides default `GATEWAY_INTERNAL_SECRET` to `"dev-internal-secret"` with no startup assertion. If the env var is unset in production, the gateway accepts any caller that knows (or guesses) the hardcoded default and can drive arbitrary fanout: `/internal/notify` will look up any `messageId`/`instructionId` and push its full content (including sender handle, content) to whatever runner socket is connected for `targetAgentId`. The comparison `req.headers["x-internal-secret"] !== INTERNAL_SECRET` is also a non-constant-time string compare (timing side-channel, lower risk). Combined with `host: "0.0.0.0"` (line 141), the internal endpoint is network-exposed.

**Fix:** Fail fast at boot if `GATEWAY_INTERNAL_SECRET` is unset/equals the dev default when `NODE_ENV==="production"`. Bind the internal HTTP server to loopback or a private interface, or split internal vs. public ports. Use `crypto.timingSafeEqual`.

### H5. Trade-room approval requirement is bypassable when the runner sets `needsApproval=false` and room.type check is the only backstop — verify business-permission gate
**File:** `apps/web/src/app/api/runner/messages/route.ts:55`

`requiresApproval = needsApproval || room.type === "trade"` correctly forces approval for trade rooms regardless of the runner's flag — good. **However**, the only thing forcing trade-room approval is the *room type*. There is no check that the **sending** agent has `can_negotiate`/`can_commit` permission at send time. `can_negotiate` is checked only when *opening* a trade room and only for the *initiator* (`rooms/route.ts:36-42`); the **responder** agent is never checked for `can_negotiate`, and neither side is checked again when actually posting trade messages. So a responder whose owner never enabled `can_negotiate` still has its runner compose and (after approval) send trade messages. Whether that is intended is a product call, but the permission model claims "identity before permission" and the responder escapes the negotiate gate entirely. At minimum this is an inconsistency to confirm.

**Fix:** If responders must also be permitted to negotiate, check `can_negotiate` on both participants at room creation, or check the sender's permission in `runner/messages` for trade rooms.

---

## Medium severity

### M1. Receipt transcript hash is non-deterministic under equal `createdAt` and races concurrent messages
**File:** `apps/web/src/app/api/rooms/[roomId]/receipts/route.ts:51-58`

```ts
const delivered = await prisma.message.findMany({
  where: { roomId, approval: { in: ["none","approved"] }, createdAt: { lte: proposal.createdAt } },
  orderBy: { createdAt: "asc" },
  select: { id, senderAgentId, content, createdAt },
});
const transcriptHash = sha256(JSON.stringify(delivered));
```

Two determinism problems:
1. **Tie-break:** `orderBy: createdAt asc` with no secondary key. `createdAt` is a millisecond `DateTime`; two messages created in the same millisecond (common when a reply + a system message land together, or under load) can be returned in arbitrary order across runs, yielding different hashes for the "same" transcript. The hash is the receipt's integrity anchor (`schema.prisma:371`), so this undermines its purpose.
2. **Boundary inclusion:** `createdAt: { lte: proposal.createdAt }` includes any *other* message sharing the proposal's exact timestamp, and its relative order vs. the proposal is undefined. If a later approval flips a message to `approved` with an earlier `createdAt`, re-computing the hash later (e.g. for verification) would now include a row that wasn't there at receipt time — but `terms` is snapshotted while `transcriptHash` is recomputable only if the delivered set is stable, which it is not (a held message approved after the receipt, with `createdAt <= proposal.createdAt`, would be retroactively included).

**Fix:** Add `{ id: "asc" }` as a stable secondary sort. Filter `id != proposal.id` then append the proposal deterministically, or include `inReplyToId`/sequence. Consider hashing only messages whose `approval`/delivery was settled at receipt time (e.g. constrain by an explicit message-id list or a sequence column) so the hash is reproducible and immutable.

### M2. Receipt creation is not atomic with its uniqueness guard — double-confirm race
**File:** `apps/web/src/app/api/rooms/[roomId]/receipts/route.ts:38-68`

The check `if (proposal.receipt)` (line 38) and `contractReceipt.create` (line 60) are separate. The DB `@unique` on `proposalMessageId` (`schema.prisma:369`) ultimately prevents two receipts, but two concurrent confirms both pass the line-38 check, both proceed, one `create` throws a Prisma P2002, and that throw is **unhandled** → 500 to the user plus a partial side effect: the losing request may already have computed the hash and will not roll back the system message / notifications (those are created *after* the receipt at lines 71-90, so the loser won't reach them — acceptable — but the 500 is a poor UX and the unique violation is uncaught).

**Fix:** Wrap in `try/catch` for P2002 and return the friendly 409, or do `create` first inside a transaction and treat the unique violation as "already confirmed".

### M3. Receipt acceptor ownership is under-checked: any room participant's owner can confirm a counterpart proposal, including a third agent
**File:** `apps/web/src/app/api/rooms/[roomId]/receipts/route.ts:28-44`

`myParticipant` is "any participant whose agent is owned by me" and the only block is `proposal.sender.ownerId === user.id` (can't confirm your own proposal). The invariant says "only the counterpart can confirm." In the 1:1 MVP this coincides, but the room model permits >2 participants (nothing enforces exactly two). If a room ever has 3 participants, a *bystander* owner (neither proposer nor intended counterpart) could confirm the proposal and create a binding receipt with `acceptedById = bystander`. Also, `myParticipant.agentId` is used as the system message sender (line 75) — a bystander's agent would author the "합의 확정" system message.

**Fix:** Enforce that the confirmer is *the* counterpart of the proposal's sender (the other participant of the 1:1), not merely "some participant that isn't the sender's owner." Assert participant count == 2 for trade rooms, or resolve the counterpart explicitly relative to `proposal.senderAgentId`.

### M4. `attestSource` accepts an unauthenticated-against-schema body and can null out config fields; `tenantId`/`spaces` overwrite with `undefined`
**File:** `apps/web/src/app/api/runner/sources/[sourceId]/attest/route.ts:18-35`

The body is cast `as AttestSourcePayload` with no zod validation. Fields like `tenantId`, `manifestHash`, `nodeCount`, `spaces` are written directly; if the runner omits them, they are written as `undefined`, which Prisma stores by dropping the key (so prior values like a previously-attested `tenantId` are lost on re-attest). More importantly, `packId: body.packId ?? prevConfig.packId` is the only fallback; a malformed body with `packId: 123` (number) or arbitrary extra keys is stored verbatim into the JSON `config`, which downstream `opencrabSourceConfigSchema` consumers (or the runner's `manual` cast in `agent-loop.ts:46`) assume is well-typed. No type errors thrown here, but later readers can break.

**Fix:** Validate `body` with `attestSourcePayloadSchema` (zod). Merge only defined fields; preserve previous values when a field is absent.

### M5. Runner `agent-loop.ts` casts JSON config without validation → throws on malformed `manual_profile`
**File:** `apps/runner/src/agent-loop.ts:44-55`

`const c = manual.config as ManualProfileConfig;` then reads `c.tastes`, etc. If `config` is `null` or a non-object (DB JSON can be anything, and `attest`/seed paths don't guarantee shape), property access on `null` throws and `syncSources` is called from `drainInbox` (`agent-loop.ts:177`) inside the WS `open` handler — an uncaught throw there rejects the drain promise (caught at `ws-client.ts:30`, logged) so the runner silently fails to load persona and may skip draining messages enqueued after the throw point. Low blast radius but a real null-deref.

**Fix:** `manualProfileConfigSchema.safeParse(manual.config)` and skip on failure.

### M6. Gateway presence: stale-sweep `terminate()` can race the `close` handler and leave `runners` map inconsistent / wrong presence
**File:** `apps/gateway/src/index.ts:200-222`

The sweep (line 211) does `runners.delete(agentId)` and `setStatus(offline)` directly, then `ws.terminate()`. `terminate()` triggers the socket's own `close` handler (line 200), whose guard is `if (runners.get(agentId) === ws)`. Because the sweep already deleted the entry, the guard is false and the close handler no-ops — fine. **But** if a *new* connection for the same agent arrives between the sweep's `delete` and the `terminate()`-induced close, the close handler's guard could compare against the new socket. More concretely: the sweep sets `offline` for an agent that may reconnect microseconds later; the reconnect sets `online` (line 172) but if the sweep's async `setStatus(offline)` (awaited *after* the reconnect's update due to interleaving) lands last, the agent is shown offline while actually connected. Presence updates are fire-and-forget `update`s with no ordering/versioning.

**Fix:** Guard `setStatus`/map mutation under a check that the socket being swept is still the current one (`if (runners.get(agentId) === ws)` before deleting), and/or serialize presence writes per agent. Use a monotonic "last transition" guard so a stale `offline` cannot overwrite a newer `online`.

### M7. `POST /api/runner/messages` allows posting after counterpart cannot receive — and ignores `senderAgentId` permission `can_speak`
**File:** `apps/web/src/app/api/runner/messages/route.ts:34-73`

There is no check that the sending agent has `can_speak`. The constitution claims speak is always on, and the schema defaults it true, but a user could set it false via raw DB / future UI; the route would still send. Lower priority since no UI toggles it off today. Noted for completeness.

### M8. `verificationRequest` requestedLevel is hardcoded to L2 but admin grants `requestedLevel` arbitrarily — and badge `kind` can desync on type change
**Files:** `apps/web/src/app/api/agents/[agentId]/verification/route.ts:25`, `admin/verification/[requestId]/route.ts:31-45`

User requests are always `L2` (fine for MVP). On approval the admin route sets `agent.verificationLevel = request.requestedLevel` and upserts the badge with `kind: request.agent.type`. If the agent's `type` changed between request and review, the badge `kind` reflects the *current* type, not the type at request time — minor consistency issue. No correctness break. Low/med.

---

## Low severity

### L1. `notifyUser` swallows errors (correct) but `notifyGateway` is awaited and could still delay the response
**Files:** `apps/web/src/lib/notify.ts:18-22`, `lib/gateway.ts:11-21`

Both are wrapped/try-caught so failures don't break the main action — invariant #8 holds. `notifyGateway` uses a 3s `AbortSignal.timeout`, so a hung gateway adds up to 3s latency to the message POST (still returns 201). Acceptable; consider fire-and-forget (don't `await`) since DB drain is the fallback.

### L2. `next.config`/auth: `ALLOW_DEV_LOGIN` defaults on in any non-production `NODE_ENV`
**File:** `apps/web/src/auth.ts:16-17`

`allowDevLogin = ALLOW_DEV_LOGIN==="true" || NODE_ENV!=="production"`. Passwordless email login (anyone types any email → account, and `ADMIN_EMAILS` match → instant admin) is enabled whenever `NODE_ENV` is unset or `"development"`/`"test"`. A misconfigured deploy (env var not set to `production`) silently exposes admin impersonation. Verify deploy sets `NODE_ENV=production`.

### L3. Inbox/messages N+1 and unbounded fanout candidate
**Files:** `apps/web/src/app/api/runner/inbox/route.ts:10-53`, `gateway index.ts:175-181`

Inbox does `roomParticipant.findMany` → `message.findMany({ roomId: { in: roomIds } })`. Fine (single query each). The gateway `pendingCount` query uses a nested `room: { participants: { some: { agentId } } }` filter on `message.count` — there is **no index** supporting `Message` filtered by participant membership; on large data this is a slow correlated query run on *every* runner connect. `Message` has `@@index([roomId, createdAt])` and `([senderAgentId, status])` but nothing for the "messages in rooms I'm in, not from me, pending" access pattern. Med-ish performance, listed low since MVP scale.

**Fix:** Consider a covering index or denormalized recipient field; or compute pendingCount via the `roomParticipant`→`roomId` list like the inbox does.

### L4. `RoomQueue.capReached` drops jobs silently and never reschedules them
**File:** `apps/runner/src/queue.ts:29-38`

When the hourly cap is hit, `enqueue` logs and **returns without queuing** (line 32). The comment claims "it stays pending and drains later," but nothing re-drains it — the in-memory job is gone; it only re-appears if the runner reconnects and calls `drainInbox` (which re-reads DB pending rows). For a *push* (`room.message`/`room.instruction` over WS) that is dropped at the cap, there is no reconnect, so the item is **not** processed until the next reconnect/drain (which may be never if the socket stays up). Counterpart waits indefinitely. Also `recordReply()` is called by the loop *after* a successful reply (`agent-loop.ts:130,164`), but `capReached` is checked at `enqueue` time — so the cap counts *completed* replies, not *enqueued* work; a burst can enqueue many jobs before any `recordReply`, overshooting the cap.

**Fix:** On cap, schedule a delayed re-drain (timer) or keep the job in the per-room queue and re-check the cap in `pump`. Count enqueues toward the cap if the intent is to cap work admitted, not just completed.

### L5. `RoomQueue.pump` worker-pool fairness / starvation
**File:** `apps/runner/src/queue.ts:40-58`

`pump` iterates `this.queues` (insertion order Map) and starts the first eligible room. A room continuously receiving messages can be re-added and, combined with FIFO, doesn't starve others (active set prevents same-room concurrency), but there's no round-robin — under sustained load the iteration always starts from the first Map entry, so later rooms can wait longer. Minor fairness issue, not a correctness bug.

### L6. `parseBrainOutput` brace-slice can corrupt content containing braces
**File:** `apps/runner/src/brain/adapter.ts:16-27`

It takes `indexOf("{")`..`lastIndexOf("}")`. If the model emits prose before/after JSON *and* the content field legitimately contains `}` followed by trailing model commentary, the slice still works; but if the model returns no JSON, the whole text is sent as content with `needs_approval:true` (safe default — good). Edge: a JSON object embedded inside a larger non-JSON message could be mis-sliced. Low; the safe-default mitigates harm.

### L7. `pairing` DELETE sets agent offline but doesn't disconnect the live gateway socket
**File:** `apps/web/src/app/api/agents/[agentId]/pairing/route.ts:29-42`

Deleting the `RunnerDevice` invalidates future token *auth*, but an already-connected runner socket on the gateway keeps its WS open (the gateway only checks the token at connect). Until the heartbeat sweep or a reconnect, a de-paired device keeps receiving fanout and can keep posting via REST (REST re-checks the token each call, so REST is fine; the **live WS push** is the gap). Presence is forced offline in DB but the socket still streams.

**Fix:** Have the web app signal the gateway to drop the agent's socket on de-pair, or have the gateway periodically re-validate the device token.

### L8. `attest`/sources expose `config` JSON to runner inbox without stripping — acceptable but note
**File:** `apps/web/src/app/api/runner/inbox/route.ts:49-52`

`agentSource.config` is returned wholesale to the runner. The schema comment says only non-secret metadata is stored, and the runner is the owner's own device, so this is fine. No leak across owners (filtered by `agentId === device.agentId`).

---

## Ownership-check audit (invariant #5)

| Route | Mutates | Ownership check | Verdict |
|---|---|---|---|
| `rooms/route.ts` POST | creates room | `userOwnsAgent(initiator)` ✓; target only existence | OK (target need not be owned) |
| `rooms/[roomId]/route.ts` PATCH | open/close room | any participant owner ✓ | OK |
| `rooms/[roomId]/instructions` POST | create instruction | participant-owner ✓ | OK |
| `rooms/[roomId]/receipts` POST | create receipt | participant-owner + not-sender, **but not strictly counterpart** | see M3 |
| `approvals/[approvalId]` POST | approve/reject | `approval.agent.ownerId===user.id` ✓ | OK |
| `agents/[agentId]/permissions` PATCH | perms | `userOwnsAgent` ✓ | OK |
| `agents/[agentId]/pairing` POST/DELETE | pairing/device | `userOwnsAgent` ✓ | OK |
| `agents/[agentId]/verification` POST | request | `userOwnsAgent` ✓ | OK |
| `admin/verification/[requestId]` POST | review | role admin ✓ | OK |
| `runner/messages` POST | message/instruction | device token + participant ✓; **inReplyTo not validated** | see H1/H2 |
| `runner/instructions/[id]/fail` POST | fail instruction | device + `instruction.agentId===device.agentId` ✓ | OK |
| `runner/sources/[id]/attest` POST | source config | device + `source.agentId===device.agentId` ✓; **no body validation** | see M4 |
| `runner/rooms/[id]/history` GET | read | device + participant ✓ | OK |
| `messages` GET / `inbox` GET | read | participant / device ✓ | OK |

No route mutates without *some* check, but `receipts` (M3) and the `inReplyTo` write (H2) are under-scoped.

---

## Prisma observations (invariant #7)

- `onDelete`: `Message.inReplyTo` relation `"replies"` has **no** `onDelete` set → defaults to `Restrict`/`SetNull` behavior; deleting a replied-to message while replies reference it can fail or orphan. `ContractReceipt.proposal` is `Cascade` — deleting a confirmed proposal message deletes the receipt (the immutable record!), which contradicts "영수증은 불변" (`schema.prisma:372,376`). A proposal message deletion (e.g. cascade from agent/room delete) silently erases the binding receipt. **Med.** Consider `Restrict` on the proposal relation or denormalizing enough into the receipt to survive message deletion.
- JSON assumptions: `Agent.permissions` read as `as { can_negotiate?: boolean } | null` in `rooms/route.ts:36` and `permissionsSchema.parse(agent?.permissions ?? {})` in `permissions/route.ts:23`. The latter is safe; the former tolerates null. `AgentSource.config` cast unsafely (M4, M5). `VerificationRequest.evidence` written as object literal — fine.
- Missing index: the gateway `pendingCount` query (L3) and `Message`-by-room-membership lacks a supporting index.

---

## Summary

**3 high (+2 spotlight) / 8 medium / 8 low.**

Highs: H1 (inReplyTo double-answer TOCTOU), H2 (inReplyToId cross-room write), H3 (codex shell injection — remote code execution on the runner host), H4 (gateway internal-secret default/exposure), H5 (responder negotiate-gate bypass). Spotlight: instruction TOCTOU = **buggy** (read-then-write, no atomic claim); trade/held-message visibility = **safe**.

**Single most important fix:** **H3 — the Codex adapter's `spawn(..., { shell: true })` with interpolated counterpart-controlled prompt text is a remote command-injection / RCE on the user's own machine.** A hostile counterpart agent can run arbitrary commands on the victim's laptop simply by sending a crafted message. Pass the prompt via stdin (or `shell: false` with an explicit binary path) immediately. The instruction/`inReplyTo` TOCTOU (spotlight + H1) is the most important *correctness* fix: replace the read-then-write with an atomic conditional `updateMany(... status: "pending")` claim inside a transaction.
