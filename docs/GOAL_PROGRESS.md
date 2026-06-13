# 목표 v3: 로드맵 R0~R5 완수 (2026-06-13 시작)

> ## ▶ 다음 작업 (콜드 재개 진입점)
> **로드맵 R0~R5 코드 완수.** 남은 건 외부 시크릿이 필요한 항목 + 선택 후속.
> 완료: R0(라이브 증명) · R1 디렉토리 · R2(노드 SDK) · R3(평판 v1+영수증 이행/분쟁+ingest 경로) · R4(Commerce Room) · R5(capability 생태계).
> 잔여 외부의존(시크릿 주입 시 가동): ① R0 OpenCrab 페르소나 실증(ocm_ 토큰) ② R1 텔레그램 브리지(봇 토큰 + /api/bridge/pair) ③ R3 ingest 실제 ontology_ingest 도구명/호출 확인(ocm_ 토큰).
> 선택 후속: 러너 자체를 node-sdk 위로 재구현(R2), capability 소유자 수동 편집 UI, 평판 trustScore 디렉토리 노출.
> 재개 순서: ① 이 파일 + docs/ROADMAP.md 읽기 ② `docker compose up -d` (DB) ③ web(next build→start)/gateway 기동 ④ 잔여/후속 착수 ⑤ 단계별 커밋(main + review-head re-parent on 8b8917e) + smoke(65+10)+integration(5)로 검증.
> git: main 로컬 커밋 완료(R3 6a8f8e1·R4 bcdc548·R5). **푸시 보류** — origin push는 사용자 명시 승인 필요(분류기가 차단). 커밋 메시지는 반드시 `git commit -F <file>` (bash에서 `@'...'@` 금지).


> **세션이 끊겨도 이 파일 + docs/ROADMAP.md를 읽고 이어서 작업한다.** (cron `opencanal-goal-resume` 5시간 주기)
> 작업 디렉토리: C:\Logotekton\OpenCanal. 서버: web :3000, gateway :8787, postgres :5433(docker).
> git: main 단일 흐름 + review-head(PR #1, 빈 base 8b8917e에 re-parent). 커밋 메시지는 `git commit -F <file>`로(헤어 here-string 금지).

## 미션 / 전략
AGI 시대 개인 agent가 개인을 대신한다 → 검증된 agent 플랫폼. 경쟁(Moltbot/OpenClaw/Hermes)과 런타임으로 경쟁하지 않고, 그들이 OpenCanal 검증 노드가 되게 한다(R2 어댑터). 상세: docs/ROADMAP.md, 메모리 strategy-positioning.

## 베이스라인 (완료)
MVP 배포가능 + 11개 에이전트 테스트 통과. smoke: scripts/smoke.mjs(65) + apps/gateway/scripts/smoke2.mjs(10) + node-sdk integration(5). 검증 루틴: `next build` + tsc(gateway/runner/node-sdk/shared) + tsup + 두 smoke + integration(`pnpm --filter @opencanal/node-sdk exec tsx scripts/integration.ts`). 서버 재기동 시 prod는 `next build`→`next start`(dev가 .next를 덮으므로), 또는 preview_start(dev). DB 죽었으면 docker compose up -d. 주의: tsx watch(gateway dev)가 @prisma/client DLL을 잡으면 `prisma generate`가 EPERM — 게이트웨이 종료 후 generate.

## 체크리스트

### R0 — 라이브 증명 ✅ (docs/R0-live-proof.md)
- [x] 실제 Claude 두뇌로 두 agent 룸 대화 — apps/runner/scripts/live-proof.ts, 4턴 자연 대화, constitution 준수(커밋 보류·환각 억제) 확인
- [~] OpenCrab 페르소나 — 토큰 주입 경로 구현됨, manual_profile로 증명. 사용자 ocm_ 토큰으로 재실행 시 완료
- [x] transcript 기록

### R1 — 배포·마찰 (docs/R1-distribution.md)
- [x] 디렉토리 UI /directory — 검색·유형필터·검증우선, 브라우저 검증(카드 50, 네비 링크), next build 컴파일 확인
- [x] 러너 설치 가이드 (엔드유저 npx 흐름)
- [~] 텔레그램 브리지: 설계 완료(롱폴링/지시/승인/푸시), 봇 토큰 + `/api/bridge/pair`(runner-auth 재활용) 구현 시 가동 — R1 잔여
- [x] 검증: web build, smoke 41+10

### R2 — 노드 프로토콜 & 어댑터 (최대 베팅) ✅ 핵심 완료
- [x] docs/NODE_PROTOCOL.md — 페어링/WS/inbox/reply/instruction + 멱등성·승인 계약 명세
- [x] packages/node-sdk — OpenCanalNode(pair/connect/drain/compose/reply) + in-flight 데듀프 + 409 멱등 처리
- [x] 첫 어댑터 예제 — packages/node-sdk/examples/generic-adapter.ts (Moltbot/Hermes/커스텀 wiring 지점 1개)
- [x] constitution 주입 — SDK가 buildConstitution()을 모든 작성에 강제, fakeBrain이 주입 검증
- [x] 검증: SDK/shared/runner tsc 클린, integration.ts 4개 통과(두 SDK 노드 WS로 지시→메시지→자동응답)
- [x] DRY: 파싱 단일출처 parseBrainOutputText를 @opencanal/shared로, 러너 adapter가 위임
- [ ] (선택, 후속) 러너 자체를 node-sdk 위로 재구현 — 현재는 별도 구현 공존

### R3 — 학습 메모리 & 평판 v1 ✅
- [x] 룸 결과/ContractReceipt를 OpenCrab에 ingest — /api/runner/receipts(데이터) + OpencrabClient.ingestReceipt(ontology_ingest) + AgentLoop.ingestReceipts(상태 변화 시 재ingest, ocm_ 없으면 no-op), ws-client 연결 시 호출
- [x] 평판 v1: 응답률/승인률/이행률/분쟁률/근거점수 + 합성 신뢰점수 — packages/shared/reputation.ts(순수) + web/lib/reputation.ts(집계) + /api/agents/[id]/reputation
- [x] 영수증 생애주기 — ReceiptStatus(confirmed/fulfilled/disputed) + /api/receipts/[id] POST(fulfill|dispute, 당사자만, disputed 종착) — 이행률/분쟁률의 데이터 원천
- [x] 프로필 신뢰 신호 강화 — 프로필 TRACK RECORD에 v1 지표+신뢰점수, 디렉토리에 활동(messagesSent) 힌트, receipt 페이지 상태 chip+이행/분쟁 버튼
- [x] 검증: 스모크에 평판/이행/분쟁/러너receipts 케이스 (smoke 41→53)
- [~] 잔여: 실제 ontology_ingest 호출은 ocm_ 토큰 필요(경로·no-op만 검증). 도구명 ontology_ingest 가정 — 실토큰으로 검증 시 확정

### R4 — 말→성사 (Commerce Room) ✅
- [x] BotContract 이행 단계 — ContractReceipt.conditions(조건표 [{label,value,met}]) + /api/receipts/[id] fulfill이 met 기록, confirm 시 조건표 동봉(rooms/[id]/receipts)
- [x] 숙박/예약 vertical 최소형 — shared LODGING_TEMPLATE(체크인/체크아웃/인원/총가격/취소정책/주차), 룸 확정 UI에 "숙박 조건 템플릿" 버튼(ConfirmDeal)
- [x] can_spend off 유지 — 결제 경로 없음, fulfilled는 당사자의 사실 진술. receipt 페이지에 조건표+met 표시, 러너 receipts/ingest에 조건표 포함
- [x] 검증: 스모크 9c(조건표 확정→이행→met 기록, 잘못된 조건표 400) (smoke 53→59)

### R5 — 능력(skill) 생태계 ✅
- [x] agent capability 모델 (승인 봉투 안) — AgentCapability(requiresApproval 기본 on, enabled, source manual|adapter) + /api/agents/[id]/capabilities GET + 프로필 CAPABILITIES 섹션
- [x] 어댑터 런타임 skill 매핑 — /api/runner/capabilities PUT(source=adapter 교체, 멱등) + node-sdk capabilities 옵션/syncCapabilities + generic-adapter 예제에 매핑 지점
- [x] constitution 주입 — buildConstitution이 capability 블록 주입(승인 봉투 명시), inbox가 capability 노출, 러너/SDK가 compose에 전달
- [x] 검증: 스모크 9d(동기화·공개조회·승인봉투·inbox노출·교체멱등·검증400) (smoke 59→65) + SDK integration 5(어댑터 매핑 + constitution 주입 검증)

## 진행 메모
- (2026-06-13) 목표 v3 수립. R0부터 순서 진행. 외부 시크릿 필요 항목(R0 ocm_ 토큰, R1 텔레그램 봇 토큰)은 코드를 완성해두고 env로 주입 가능하게 만든 뒤, 시크릿 없이 가능한 데까지 검증.
