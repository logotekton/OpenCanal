# OpenCanal — Data-Integrity / Prisma Data-Model Review (test2-data)

Date: 2026-06-14
Scope: Prisma/data-model correctness. Read + inspect only; no source modified.
Schema source of truth: `packages/db/prisma/schema.prisma`
Method: schema read, code grep/read, live Postgres inspection (`opencanal-postgres`),
authenticated HTTP probes against `http://localhost:3000`.

---

## 1. Relations & onDelete behavior (every FK)

| Table.column → target | onDelete | Notes / Risk |
|---|---|---|
| Notification.userId → User | Cascade | OK — notifications die with user. |
| Account.userId → User | Cascade | OK (Auth.js). |
| Session.userId → User | Cascade | OK (Auth.js). |
| Agent.ownerId → User | Cascade | OK — but Agent is the root of a deep cascade (see below). |
| VerificationBadge.agentId → Agent | Cascade | OK. |
| VerificationBadge.approvedById → User | SetNull (implicit, optional) | OK — keeps badge if approver deleted. |
| VerificationRequest.agentId → Agent | Cascade | OK. |
| VerificationRequest.reviewerId → User | SetNull (implicit, optional) | OK. |
| AgentSource.agentId → Agent | Cascade | OK. |
| RunnerDevice.agentId → Agent | Cascade | OK. |
| DevicePairing.agentId → Agent | Cascade | OK. |
| RoomParticipant.roomId → Room | Cascade | OK. |
| RoomParticipant.agentId → Agent | Cascade | OK. |
| Message.roomId → Room | **Cascade** | **RISK — see H1.** Deleting a Room wipes all messages, incl. proposal messages. |
| Message.senderAgentId → Agent | **Cascade** | **RISK — see H1.** Deleting an Agent wipes every message it ever sent. |
| Message.inReplyToId → Message | SetNull (implicit, optional) | OK — reply chains survive parent deletion. |
| ApprovalRequest.messageId → Message | Cascade | OK. |
| ApprovalRequest.agentId → Agent | Cascade | OK. |
| Instruction.roomId → Room | Cascade | OK. |
| Instruction.agentId → Agent | Cascade | OK. |
| **ContractReceipt.proposalMessageId → Message** | **Cascade** | **H1 — the core finding.** |
| ContractReceipt.roomId → Room | **Cascade** | **H1 — second path to the same data loss.** |
| ContractReceipt.acceptedById → User | Restrict (implicit, required) | OK — a user with accepted receipts cannot be hard-deleted (blocks the User cascade). Good for integrity, but note it makes `User` deletion fail loudly rather than orphan a receipt. |

Verified live (DB-level `confdeltype`): `ContractReceipt_proposalMessageId_fkey = c` (cascade),
`ContractReceipt_roomId_fkey = c` (cascade), `ContractReceipt_acceptedById_fkey = r` (restrict).

---

## 2. Findings

### H1 — "Immutable" ContractReceipt is destroyed when its proposal Message (or Room) is deleted  [HIGH]

Table/column: `ContractReceipt.proposalMessageId → Message (onDelete: Cascade)` and
`ContractReceipt.roomId → Room (onDelete: Cascade)`.
File: `packages/db/prisma/schema.prisma:376` (proposal relation), `:375` (room relation),
`:338` (Message.roomId Cascade), `:339` (Message.senderAgentId Cascade).

The receipt is documented as an immutable record ("제안이 수정되어도 영수증은 불변",
schema:372). The `terms` column is a content snapshot and survives proposal *edits* —
but **not proposal deletion**. Because the FK cascades, deleting the proposal Message
silently deletes the receipt itself.

Empirically confirmed in the live DB (transaction rolled back):

```
NOTICE: receipt cmqb0urpz000zd0es2u9stcbt existed_before=1 existed_after_message_delete=0
```

Two practical destruction paths to the same outcome:
- Delete the Room → `Message.roomId` cascade removes every message incl. the proposal →
  `ContractReceipt.proposalMessageId` cascade removes the receipt. (Room cascade → messages
  → receipts, exactly the chain flagged in scope.)
- Delete the sender Agent → `Message.senderAgentId` cascade removes the proposal → receipt gone.
  Agent deletion in turn cascades from User deletion (`Agent.ownerId` Cascade), so deleting
  the *counterpart* user erases the receipt that the *other* party relied on.

Mitigating fact (current state): **no application code path deletes Message, Room, or Agent.**
Grep for `prisma.message.delete*`, `room.delete`, `agent.delete` finds none; the only deletes
in the codebase are `runnerDevice.deleteMany` / `devicePairing.deleteMany`
(`apps/web/src/app/api/runner/pair/route.ts:32`, `apps/web/src/app/api/agents/[agentId]/pairing/route.ts:16,38`)
and in-memory `Map.delete` in the gateway/runner. So the bug is **latent**: it cannot be
triggered through the MVP API today, but any future "delete my agent / close & purge room /
GDPR user-delete" feature, or a manual admin/DB delete, will destroy supposedly-immutable
contract evidence with no error.

Failure scenario: party A's agent proposes terms, party B confirms → receipt created with
transcript hash. Later A deletes their agent (or an admin removes the room) → B's legally-meaningful
receipt and its transcript hash vanish. The "BotContract Evidence Package" guarantee is broken.

Suggested fix: make the receipt the durable anchor instead of a cascade leaf.
- Change `ContractReceipt.proposalMessageId` relation to `onDelete: Restrict` (or `SetNull` with
  the column made optional), and `ContractReceipt.roomId` to `Restrict`/`SetNull`. The receipt
  already snapshots `terms` + `transcriptHash`, so it does not need the live Message/Room to remain
  meaningful. Restrict turns an accidental purge into a loud FK error rather than silent evidence loss.
- If hard-delete of agents/rooms is ever required, implement soft-delete (status flag) rather than
  physical delete, so receipts and their proposal messages are retained.

### M1 — `pendingCount` membership query has no index support for the `senderAgentId <> agentId` filter  [MEDIUM]

File: `apps/gateway/src/index.ts:191-197`.

```ts
prisma.message.count({
  where: {
    room: { participants: { some: { agentId } } },
    senderAgentId: { not: agentId },
    status: "pending",
  },
})
```

Runs on **every runner WS connect**. The existing index `Message_senderAgentId_status_idx`
`(senderAgentId, status)` cannot serve `senderAgentId <> X` (negation is not an index seek).
The planner is left to filter `(senderAgentId <> X AND status='pending')` on Message and hash-join
to `RoomParticipant`. Live EXPLAIN (tiny table) confirms a `Seq Scan on "Message"` for that branch.
At volume (many messages per agent), every reconnect storm becomes a Message table scan.

Suggested fix: drive the count by membership + status, which *are* indexable. Either add a
composite index `@@index([roomId, status])` on Message and let Prisma filter the small `<> agentId`
residue in memory, or rephrase to filter on `roomId IN (myRooms)` (sub-query) + `status` so the
planner can use `(roomId, ...)`. Practically: add `@@index([roomId, status])` to Message.

### M2 — Inbox messages query: no composite index covering the hot filter  [MEDIUM]

File: `apps/web/src/app/api/runner/inbox/route.ts:17-30`. Filter:
`roomId IN [...] AND senderAgentId<>self AND status='pending' AND approval IN ('none','approved')
ORDER BY createdAt ASC`. Runs on every inbox drain.

Existing `Message_roomId_createdAt_idx` `(roomId, createdAt)` partially helps (per-room range +
order), but `status` and `approval` are not in any index, so they are post-filter residue. For a
room with a long message history this reads/sorts far more rows than the few pending ones. Similar
shape for the gateway query (M1).

Suggested fix: add `@@index([roomId, status, createdAt])` (or `[roomId, status, approval, createdAt]`)
on Message. This covers the per-room pending lookup with ordering and makes both the inbox drain and
a rephrased pendingCount index-only-ish.

Note: the `Instruction` query (`agentId+status`, inbox:31-32) is **well covered** by the existing
`Instruction_agentId_status_idx`. No change needed there.

### L1 — Unguarded JSON casts on Agent.permissions / AgentSource.config / Message.claims  [LOW]

`Agent.permissions` is cast with a bare `as` (not validated) in the trade gate:
`apps/web/src/app/api/rooms/route.ts:37` and `:44`
`const initiatorPerms = initiator.permissions as { can_negotiate?: boolean } | null;`
This does not throw on malformed data (a TS cast is a no-op at runtime) and treats a missing/odd
value as falsy → the worst case is over-restriction (deny the trade room), not a crash. A `null`
JSON also just fails the `?.can_negotiate` check → deny. So the **trade gate is safe** against
null/legacy permissions (fails closed).

The permissions **PATCH** is stricter: `apps/web/src/app/api/agents/[agentId]/permissions/route.ts:23`
`permissionsSchema.parse(agent?.permissions ?? {})`. `null ?? {}` → `{}` is handled (all fields have
zod defaults). **But** a *malformed non-null* object (e.g. legacy `{can_negotiate:"yes"}` or a JSON
array) would make `permissionsSchema.parse(...)` **throw**, surfacing as an unhandled 500 on the PATCH.

`AgentSource.config` is cast `as ManualProfileConfig` without validation in the runner
(`apps/runner/src/agent-loop.ts:45`) — tolerant (only reads optional string fields), low risk.
`Message.claims` is validated on write (`runner/messages` route uses `brainOutputSchema.shape.claims`)
and only read defensively (`apps/runner/src/cli.ts:177` `output.claims?.length`). Low risk.

Live DB shows **all current data is well-formed**: 92 Agent rows all `jsonb_typeof = object`,
0 null / 0 non-object permissions; all 22 AgentSource.config are objects; Message.claims are
array-or-null only. So this is latent (legacy/manual-edit risk), not an active break.

Suggested fix: in the permissions PATCH, use `permissionsSchema.safeParse(agent?.permissions ?? {})`
and fall back to schema defaults on failure (or `.catch(defaults)` via zod), so a corrupt row
self-heals instead of 500-ing. Optionally validate the trade-gate read with the same schema for
consistency.

---

## 3. Items verified OK (no finding)

### Item 4 — Enums vs string columns; directory `?type` validation  [VERIFIED FIXED]
- `AgentSource.kind` is a plain **String** (schema:239) — a code registry key, intentionally not an
  enum. `Instruction.status` (`InstructionStatus`) and `Message.status` (`MessageStatus`) /
  `Message.approval` (`ApprovalState`) are **enums** (schema:90-94, 76-88).
- `apps/web/src/app/api/agents/directory/route.ts:15-17` whitelists `type` against the five
  AgentType values and falls back to `null` (no filter) for anything else, so an invalid enum never
  reaches Prisma's `where`.
- **Authenticated live probes** (dev-email session):
  - `GET /api/agents/directory?type=garbage` → **200**, 50 agents (filter dropped). ✅
  - `?type=business` → 200, 1 agent (filter applied correctly).
  - `?type=L0xx` → 200, 50 agents. `?type=personal' OR 1=1` (encoded) → 200, 50 agents (Prisma
    parameterizes; no injection, no 500). `no type` → 200, 50 agents.
  The "should be fixed" expectation holds.

### Item 5 — Uniqueness constraints and P2002 handling  [VERIFIED]
All `@unique` constraints exist in the live DB (verified via `pg_indexes`):
- `Agent.handle` → `Agent_handle_key` (UNIQUE). User-triggered create catches **P2002** →
  409: `apps/web/src/app/api/agents/route.ts:61` (and a pre-check at :25). ✅
- `RunnerDevice.tokenHash` → `RunnerDevice_tokenHash_key` (UNIQUE), `RunnerDevice.agentId` →
  `RunnerDevice_agentId_key` (UNIQUE). Pairing flow deletes-then-creates inside a transaction
  (`runner/pair/route.ts:32-33`), so collision is structurally avoided.
- `DevicePairing.code` → `DevicePairing_code_key` (UNIQUE). Generated server-side.
- `ContractReceipt.proposalMessageId` → `ContractReceipt_proposalMessageId_key` (UNIQUE). The
  confirm path catches **P2002** → 409 on concurrent confirm
  (`apps/web/src/app/api/rooms/[roomId]/receipts/route.ts:74`), plus a pre-check at :38. ✅
- `VerificationBadge.agentId` → `VerificationBadge_agentId_key` (UNIQUE) — one badge per agent.
- `ApprovalRequest.messageId` → `ApprovalRequest_messageId_key` (UNIQUE) — one approval per message.
- Auth.js uniques (`User.email`, `Session.sessionToken`, `Account[provider,providerAccountId]`,
  `VerificationToken`) all present.
- No bare user-triggered create on a unique column is missing P2002 handling.

### Item 6 — Migrations match schema; lock present  [VERIFIED]
- Three migrations on disk: `20260611140149_init`, `20260612134431_add_instructions`,
  `20260612142143_notifications_receipts`. `migration_lock.toml` present (`provider = "postgresql"`).
- All three are `finished_at` set, `rolled_back_at` NULL in `_prisma_migrations` (live).
- Cross-checked the SQL DDL against the current schema: all 13 tables, all enums, all `@@index`
  and `@unique` declarations, and every FK `onDelete` match the live DB exactly (41 indexes
  enumerated; ContractReceipt FK delete types confirmed c/c/r). **No drift detected.**
- The migration SQL even encodes the H1 cascade explicitly:
  `notifications_receipts/migration.sql:44` `ContractReceipt_proposalMessageId_fkey ... ON DELETE CASCADE`
  — i.e. the risk is baked into the migration, not an out-of-band change.

---

## 4. Severity summary

| ID | Severity | Area | One-line |
|----|----------|------|----------|
| H1 | HIGH | onDelete cascade | Receipt is a cascade leaf of Message/Room/Agent — proposal/room/agent deletion silently erases "immutable" contract evidence (confirmed in DB). Latent today (no delete code path). |
| M1 | MEDIUM | index | Gateway pendingCount `senderAgentId <> id` can't use existing index → Message seq scan on every reconnect. |
| M2 | MEDIUM | index | Inbox messages filter on status/approval uncovered by any index → over-reads at volume. Add `@@index([roomId, status, createdAt])`. |
| L1 | LOW | JSON cast | permissions PATCH `permissionsSchema.parse()` throws (500) on malformed non-null JSON; trade-gate `as` cast fails-closed (safe). All current data clean. |
| — | OK | enum/dir | `?type=garbage` → 200 verified live; whitelist fix confirmed. |
| — | OK | uniqueness | All uniques enforced; P2002 caught on agent create + receipt confirm. |
| — | OK | migrations | 3 migrations + lock, applied, zero drift vs schema and live DB. |
