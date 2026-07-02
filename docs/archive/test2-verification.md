# OpenCanal QA — Verification & Badge Lifecycle (test2)

- **Date:** 2026-06-14
- **Target:** Next.js API @ `http://localhost:3000` (local dev)
- **Method:** Node `fetch` + cookie jar, dev-email auth (`/api/auth/csrf` → `/api/auth/callback/dev-email` → `/api/auth/session`), `redirect: "manual"`. DB cross-checks via `docker exec opencanal-postgres psql` (Postgres on host port **5433**).
- **Accounts:** normal user `t2-verif-uxglhe@test.com` (role `user`), escalation user `t2-verif-ijv2pa@test.com` (role `user`), admin `ghddudxor12@gmail.com` (role `admin`, confirmed via session).
- **Source (read-only):** `apps/web/src/app/api/agents/[agentId]/verification/route.ts`, `apps/web/src/app/api/admin/verification/[requestId]/route.ts`, `apps/web/src/components/badge.tsx`, `apps/web/src/lib/session.ts`, `apps/web/src/auth.ts`, `apps/web/src/lib/notify.ts`, `packages/db/prisma/schema.prisma`, `packages/shared/src/schemas.ts`.

---

## Results

### 1. Create agent (L1) + submit verification + duplicate → 409 — **PASS**
- `POST /api/agents` → `201 {"id":"cmqcizmo40007d06wr0apf9oh","handle":"t2agent23gzk8"}`.
- Created `verificationLevel` (via `GET /api/agents`) = **L1**. (Hardcoded in `agents/route.ts`: email login = L1; matches spec.)
- `POST /api/agents/:id/verification {note, officialUrl}` → `201 {"id":"cmqcizn5y0009d06wtwi2pu7n"}`.
- Second submit while pending → **`409 {"error":"이미 심사 대기 중인 신청이 있습니다."}`**. Correct.

### 2. Admin approve — **PASS**
- requestId obtained via DB (see friction F1).
- `POST /api/admin/verification/:requestId {decision:"approved", note:"looks good"}` (admin cookie) → **`200 {"ok":true}`**.

### 3. Post-approval state (level → L2, badge row, owner notified) — **PASS**
- `GET /api/agents` (owner): agent `verificationLevel` = **L2**.
- DB `VerificationRequest`: state `approved`, `reviewerId` = admin id, `reviewNote` = `looks good`, `requestedLevel` L2.
- DB `VerificationBadge`: **row present** — `level=L2, kind=personal, approvedById=<admin>, evidenceNote="looks good"`. (Badge color is rendered client-side as `#ff7a17` / `.sunset` orange in `badge.tsx`; no color column in the model — color is a UI constant, not persisted. Documented, not a defect.)
- `GET /api/notifications` (owner): **1** notification `kind=verification_reviewed`, title `@t2agent23gzk8 검증이 승인되었습니다 — 주황 딱지가 부여됩니다`, body `looks good`, href `/agents/t2agent23gzk8`. Correct.

### 4. Reject path (fresh request) — **PASS**
- Fresh request `cmqcizo3v000id06wew28zdsj` (esc user's agent) → `POST .../verification {decision:"rejected", note:"insufficient evidence"}` (admin) → **`200 {"ok":true}`**.
- DB `VerificationRequest`: state `rejected`, reviewer = admin, note stored.
- Agent `verificationLevel` remains **L1** (no escalation).
- DB `VerificationBadge`: **no row** for the rejected agent. Correct.
- Owner notified: `GET /api/notifications` (esc user) → `kind=verification_reviewed`, title `@t2escs0x5mj 검증이 반려되었습니다`. Correct.

### 5. AuthZ — **PASS**
- Normal user → `POST /api/admin/verification/:id {decision:"approved"}` → **`403 {"error":"forbidden"}`**. (Guard: `user.role !== "admin"` in the route.)
- **Privilege escalation via body:** esc user (role `user`) self-approving own request with body `{decision:"approved", role:"admin", user:{role:"admin"}}` → **`403 {"error":"forbidden"}`**. Role is read from the server-side JWT (`auth.ts` `jwt`/`session` callbacks → `session.ts` `getSessionUser`); body fields are ignored. The route never reads `role` from the body. **No escalation possible.** Request stayed `pending` and was subsequently rejected by admin (step 4).

### 6. Badge threshold + payload validation
- **Threshold (`isVerified`) — PASS.** Replicated `badge.tsx` logic: `L0→false, L1→false, L2→true, L3→true, L4→true, L5→true`. Unknown level (`"BOGUS"`) → `indexOf` = -1 → `false` (safe). L0/L1 NOT badged; L2+ badged. Matches spec.
- **Payload validation — FINDING (no validation).** The verification submit route does **zero** validation on the body:
  - Empty body `{}` (missing both `note` and `officialUrl`) → **`201`** (request created with `evidence:{note:"", officialUrl:""}`). No required fields.
  - 100,000-char `note` + a 5,000-char non-URL `officialUrl` → **`201`**. DB confirms the note was stored verbatim at **100,000 chars** (`length(evidence->>'note')=100000`). No max-length cap, no URL-format check.
  - Contrast: `createAgentSchema` (`packages/shared/src/schemas.ts`) uses zod with bounded lengths; the verification route uses none. See F2.

### Extra negative checks — all **PASS**
| Case | Expected | Actual |
|---|---|---|
| Submit verification, no auth cookie | 401 | `401 {"error":"unauthorized"}` |
| Submit verification on agent not owned by caller | 403 | `403 {"error":"forbidden"}` |
| Submit again with no `content-type`/body while pending | 409 | `409` (`req.json().catch(()=>({}))` tolerates it) |
| Admin re-approve an already-approved request | 404 | `404 {"error":"request not found or already reviewed"}` |
| Admin invalid `decision:"maybe"` | 400 | `400 {"error":"decision must be approved|rejected"}` |

---

## Bugs (repro)
None functional. All lifecycle, authZ, and notification behaviors are correct.

## Findings / Friction
- **F1 (friction — no admin list API):** There is no endpoint to list pending `VerificationRequest`s. An admin cannot discover a `requestId` to act on without direct DB access (`docker exec ... psql ... select id,state from "VerificationRequest"`). The whole admin approval flow is unusable via API alone. Recommend a `GET /api/admin/verification?state=pending` (or similar) returning request id, agent handle, requested level, evidence.
- **F2 (finding — unvalidated verification payload, low/medium risk):** `POST /api/agents/:id/verification` accepts arbitrary, unbounded `note`/`officialUrl`. A 100k-char note is persisted verbatim into the `evidence` JSON column; `officialUrl` is never validated as a URL; both default to `""` when absent. This is a DoS/storage-bloat and data-quality vector. Recommend a zod schema (e.g. `note: z.string().max(2000).optional()`, `officialUrl: z.string().url().max(500).optional()`), mirroring `createAgentSchema`.
- **Note (not a defect):** Badge "orange" is a front-end constant (`#ff7a17` / Tailwind `.sunset` in `badge.tsx`), not stored on `VerificationBadge`. The model has no color field. Color correctness was verified in source, not via API.
- **Note (good behavior):** `isVerified` treats unknown/garbage levels as not-verified (`indexOf` = -1), so a malformed level can't accidentally show a badge.

---

## Evidence — key IDs
- approved agent `cmqcizmo40007d06wr0apf9oh` (`@t2agent23gzk8`), req `cmqcizn5y0009d06wtwi2pu7n` → state `approved`, badge present.
- rejected agent `cmqcizo2y000gd06w8cypcn49` (`@t2escs0x5mj`), req `cmqcizo3v000id06wew28zdsj` → state `rejected`, no badge, level L1.
- validation agents `cmqcizo79000md06wjpi8d0y1` (empty body), `cmqcizo90000qd06wxfyjhfpu` (100k note) → both `pending`, no validation rejection.
