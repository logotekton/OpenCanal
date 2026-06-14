# OpenCanal QA — Trade Room Gate / Approval / ContractReceipt (test2-trade)

- **Date:** 2026-06-14
- **Target:** Next.js API at `http://localhost:3000` (local dev)
- **Method:** Node `fetch` + per-user cookie jar (`redirect:"manual"`), dev-email auth, runner pairing for Bearer.
- **Scope:** Trade gate (L1 + both `can_negotiate`), held-message approval/reject flow, ContractReceipt confirm matrix, transcript-hash stability, `can_commit`/`can_spend` lock.
- **Users:** UserA, UserB (parties), UserC (non-party third user). Unique emails `t2-trade-<rand>@test.com`.
- **Source files reviewed (read-only, not modified):**
  - `apps/web/src/app/api/rooms/route.ts` (trade gate)
  - `apps/web/src/app/api/runner/messages/route.ts` (hold-on-trade)
  - `apps/web/src/app/api/rooms/[roomId]/messages/route.ts` (visibility)
  - `apps/web/src/app/api/runner/inbox/route.ts` (runner drain)
  - `apps/web/src/app/api/approvals/[approvalId]/route.ts` (approve/reject)
  - `apps/web/src/app/api/rooms/[roomId]/receipts/route.ts` (receipt POST + transcript hash)
  - `apps/web/src/app/receipts/[receiptId]/page.tsx` (receipt GET / party gate)
  - `apps/web/src/app/api/agents/[agentId]/permissions/route.ts` (permission lock)

## Result: 23/23 checks PASS. No bugs found.

---

## 1. Trade gate — L1 + both owners `can_negotiate`

Note: agents are created at **L1 by default** (`agents/route.ts` sets `verificationLevel: "L1"` because dev-email login = email verified). So the L1+ half of the gate is satisfied automatically for normal users; the discriminating factor in practice is `can_negotiate`.

| # | Case | Expected | Status | Body |
|---|------|----------|--------|------|
| 1a | neither toggled | 403 | **403 PASS** | `{"error":"거래 룸을 열려면 내 agent의 협상 권한(can_negotiate)을 먼저 켜야 합니다. 프로필 → 권한에서 설정하세요."}` |
| 1b | only initiator toggled | 403 + **target** error | **403 PASS** | `{"error":"상대 agent가 협상 권한을 켜지 않아 거래 룸을 열 수 없습니다."}` |
| 1b2 | only target toggled | 403 + **initiator** error | **403 PASS** | `{"error":"거래 룸을 열려면 내 agent의 협상 권한(can_negotiate)을 먼저 켜야 합니다..."}` |
| 1c | both toggled | room created | **201 PASS** | `{"roomId":"cmqcj1a2z005od06w9te25zp8"}` |

**Error messages distinguish initiator vs target — confirmed.** The check order is **initiator-first** (`rooms/route.ts` L37-50): the initiator's own permission is validated before the target's. So "only initiator toggled" surfaces the *target* error, and "only target toggled" surfaces the *initiator* error. Both messages are distinct and correctly attributed.

## 2. Trade-room message is HELD

A instructs agent → A's runner posts (`needsApproval:false`, trade room forces hold via `requiresApproval = needsApproval || room.type === "trade"`).

| Check | Expected | Result |
|-------|----------|--------|
| Runner POST response | `201 {requiresApproval:true}` | **PASS** — `{"messageId":"...","requiresApproval":true}` |
| B sees via GET /rooms/:id/messages | NOT visible | **PASS** — B message count = 0 |
| A sees with approvalRequest id | visible, `approval:"required"` | **PASS** — A sees msg `approval=required`, `approvalRequest.id` present |
| B runner inbox | does NOT receive | **PASS** — B inbox messages = 0 (inbox filters `approval in [none,approved]`) |

## 3. Approve / Reject

| Check | Expected | Result |
|-------|----------|--------|
| 3 | A `POST /api/approvals/:id {approved}` | **200 PASS** `{"ok":true}` |
| 3 | B now sees the message | **PASS** — visible after approve |
| 3 | B runner inbox now receives it | **PASS** — present (status flipped to `pending`, `approval:approved`) |
| 3b | Reject a separate message | **200 PASS** — `{"ok":true}`; B does **not** see it; B inbox does **not** receive it (stays hidden, status `failed`) |
| 3c | Re-decide an already-decided approval | **404 PASS** — `{"error":"not found or already decided"}` (guarded by `state !== "pending"`) |

## 4. ContractReceipt confirm matrix

Direction: a proposal sent by **A's agent** and approved by **A** (its owner) is confirmed by **B** (the *receiving* owner). The route blocks confirming your own agent's proposal.

| # | Case | Expected | Result | Body |
|---|------|----------|--------|------|
| 4a | A confirms A's own approved proposal | 403 | **403 PASS** | `{"error":"상대의 제안만 확정할 수 있습니다."}` |
| 4b | confirm a non-approved (rejected) message | 400 | **400 PASS** | `{"error":"승인되어 전달된 제안만 확정할 수 있습니다."}` |
| 4c | confirm in a non-trade (question) room | 400 | **400 PASS** | `{"error":"합의 확정은 거래 룸에서만 가능합니다."}` |
| 4d | valid confirm (B confirms A's approved proposal) | 201 `{receiptId}` | **201 PASS** | `{"receiptId":"cmqcj1akd006jd06wm5hm93rn"}` |
| 4e | double-confirm same proposal | 409 | **409 PASS** | `{"error":"이미 확정된 제안입니다."}` |
| 4f | GET `/receipts/:id` as party A | 200 | **200 PASS** | rendered receipt page |
| 4f | GET `/receipts/:id` as party B | 200 | **200 PASS** | rendered receipt page |
| 4g | GET `/receipts/:id` as non-party C | redirect/forbidden | **PASS** | `307 → /rooms` (party check `redirect("/rooms")`) |

## 5. Transcript hash stability — STABLE (verified two ways)

**Source (`receipts/route.ts` L52-59):**
```
delivered = messages WHERE roomId, approval IN ["none","approved"], createdAt <= proposal.createdAt
            ORDER BY [createdAt asc, id asc]
            SELECT {id, senderAgentId, content, createdAt}
transcriptHash = sha256( JSON.stringify(delivered) )
```
The secondary sort key `id` (CUIDs, lexicographically unique) breaks any `createdAt` ties, so the row order is fully deterministic regardless of DB return order. The `createdAt: { lte: proposal.createdAt }` bound deliberately excludes the post-confirm system message and any later traffic, so the hash is fixed at confirm time. Comment F7 documents this intent.

**Empirical recomputation:** independently rebuilt the `delivered` array from the API and recomputed sha256 in a separate script. It matched the hash rendered on the receipt page byte-for-byte:
```
renderedHash : 73b12dca92f917dca217da5eadafa43641a9becf7a098267f0ba1083fe2211b1
recomputed   : 73b12dca92f917dca217da5eadafa43641a9becf7a098267f0ba1083fe2211b1
MATCH        : true
```

## 6. `can_commit` / `can_spend` forced false

PATCH `/api/agents/:id/permissions` with body `{can_negotiate:true, can_commit:true, can_spend:true}`:
- Result: `{"can_speak":true,"can_advise":true,"can_negotiate":true,"can_commit":false,"can_spend":false}` — **PASS**.
- The handler only reads `body.can_negotiate` and hard-codes `can_commit:false, can_spend:false` (`permissions/route.ts` L24), so the auto-payment guardrail cannot be flipped via the API.

---

## Observations (non-blocking, behavior-as-designed)
- **Gate check order is initiator-first.** Combined with default-L1 agents, the only way a normal user hits the L1 error is if an agent were demoted to L0 by an admin — not reachable in this normal-user test. The `can_negotiate` opt-in is the effective gate, and its two error strings are correctly distinct.
- **Receipt direction is owner-relative, not agent-relative.** "Confirm your own proposal → 403" is enforced on `proposal.sender.ownerId === user.id`, i.e. an owner cannot confirm a proposal authored by *their own* agent. Correct per spec.
- **`postMessageSchema` / direct message POST is removed** — `rooms/[roomId]/messages` exposes GET only; the only write path is owner→instruction→runner, as intended.
