# OpenCanal

> **내 판단력을 심은 자율 생산 agent — 밤새 일하는 분신.**
> 자는 동안 내 분신이 일하고, 아침에 실물이 와 있다.

**본질**: 만드는 것은 워크플로우가 아니라 **일꾼** — 나의 판단력(PAB 팩)을 탑재한, 실행 가능한 나의 사본이다. 팩은 사본의 정신, agent 런타임은 사본의 몸, 아침 리뷰는 사본을 나에게 수렴시키는 장치. 방향의 전문: **`docs/DIRECTION.md`**.

## 생산 루프 (P0)

```
[Plan]                [Produce]              [Review]                  [Correct]
소유자가 정책·지시·  →  밤 실행기가 카드별   →  아침에 일지를 읽고     →  반려 사유가 팩(OpenCrab)
작업 카드를 등록        산출물 생산+일지 기록    산출물 승인/반려          으로 재ingest — 사본이 배운다
(/night/plan)           (runner `night run`)     (/night)                  (다음 night run이 드레인)
```

- 모든 판단에는 정책 출처가 남는다 — 일지의 `[P:id]` 인용이 반려 교정을 정확한 정책에 겨냥시킨다.
- 두뇌는 소유자 머신에서, 소유자의 Claude 구독(Claude Agent SDK headless)으로 돈다. 플랫폼에 LLM/OpenCrab 자격증명 없음 (ocm_ 토큰은 러너 로컬 전용).
- 바깥으로 나가는 것은 항상 소유자 승인 뒤 (자동 발행 없음).

## 구조

```
apps/
  web/       Next.js 15 — /night 아침 리뷰(밤사이 일지+산출물 카드), /night/plan 정책·지시·카드 편집,
             /api/night/* (러너 큐/보고/교정 ack + 소유자 리뷰/CRUD)
  runner/    opencanal-runner CLI — `night run`: 큐 pull → 교정 재ingest → 팩 컨텍스트 → 생산 → 보고
  socket/    MCP 소켓 — 팩의 콘센트. 외부 워크플로우(n8n, Claude Code 등)가 pack_query로 판단을 읽고
             report_outcome으로 결과를 되돌린다 (stdio, 사용자 머신 로컬)
  gateway/   (v1 동결) 룸 WS 게이트웨이
  bridge/    (P2 재활용 예정) 텔레그램 — 아침 승인 채널로 환생 예정
packages/
  db/        Prisma — Night 원장(NightPolicy/NightDirective/NightTask/NightRun/NightArtifact) + v1 모델(동결)
  shared/    night 프로토콜(zod 계약, buildNightConstitution, parseNightBrainOutput) + v1 constitution
  node-sdk/  (v1) 외부 런타임 연결 SDK
docs/
  DIRECTION.md   방향의 원천 (피벗 v2)
  archive/       v1(신뢰 네트워크) 시대 문서 — 실패의 기록이 근거다
```

## 개발 시작

```powershell
# 0) 사전 준비: Node 20+, pnpm, Docker Desktop
pnpm install
docker compose up -d                  # Postgres :5433
pnpm db:migrate                       # night_loop 마이그레이션 포함

# 1) 웹 (아침 리뷰 + API)
pnpm --filter @opencanal/web dev      # http://localhost:3000

# 2) 러너 (소유자 머신 — agent의 두뇌)
pnpm --filter opencanal-runner dev login          # 웹 → Runner 설정 → 페어링 코드
pnpm --filter opencanal-runner dev link opencrab  # ocm_ 토큰 연결 (교정 재ingest·팩 컨텍스트)
pnpm --filter opencanal-runner dev night run      # 밤 1회전 (--dry로 예행)

# 3) MCP 소켓 (선택 — 외부 워크플로우에 팩 꽂기)
pnpm --filter opencanal-socket build
# Claude Code 등: claude mcp add opencanal-socket -- node apps/socket/dist/index.js
```

P0 루프 검증 순서: `/night/plan`에서 정책 몇 개 + 작업 카드 1장 등록 → `night run` → `/night`에서 일지 확인, 반려+사유 → 다시 `night run` (교정이 팩으로 ingest되고 행동이 달라지는지).

## 디자인

- 표면: `DESIGN-x.ai.md` — #0a0a0a 다크 캔버스, hairline 보더, 주황(#ff7a17)
- 타이포그래피/인터랙션: `DESIGN-tesla.md` — Pretendard Variable, weight 400/500만, 절제된 스케일
- 토큰: `apps/web/src/app/globals.css`의 `@theme`

## v1 (동결)

이 레포는 "검증 agent 신뢰 네트워크"(룸·검증 딱지·평판·영수증)로 시작했다 — 코드는 동결 상태로 남아 있고(웹의 룸/디렉토리/관리자 화면, gateway, node-sdk), 왜 접었는지는 `docs/DIRECTION.md`의 기각 기록과 `docs/archive/`에 있다. v1의 승인 게이트·Receipt·rigor 사상은 night 루프의 리뷰·원장·provenance로 환생했다.
