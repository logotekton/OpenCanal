# 목표 v3: 로드맵 R0~R5 완수 (2026-06-13 시작)

> ## ▶ 다음 작업 (콜드 재개 진입점)
> **R3 — 학습 메모리 & 평판 v1**부터. 외부 시크릿 불필요, 전부 빌드·테스트 가능.
> 완료: R0(라이브 증명) · R2(노드 SDK) · R1 디렉토리. 잔여 외부의존: R0 OpenCrab(ocm_ 토큰), R1 텔레그램 브리지(봇 토큰).
> 재개 순서: ① 이 파일 + docs/ROADMAP.md 읽기 ② `docker compose up -d` (DB) ③ web/gateway 기동 ④ R3 착수 ⑤ 단계별 커밋(main + review-head re-parent on 8b8917e) + smoke(41+10)로 검증.
> git: 깨끗하고 origin/main 푸시됨. 커밋 메시지는 반드시 `git commit -F <file>` (bash에서 `@'...'@` 금지).


> **세션이 끊겨도 이 파일 + docs/ROADMAP.md를 읽고 이어서 작업한다.** (cron `opencanal-goal-resume` 5시간 주기)
> 작업 디렉토리: C:\Logotekton\OpenCanal. 서버: web :3000, gateway :8787, postgres :5433(docker).
> git: main 단일 흐름 + review-head(PR #1, 빈 base 8b8917e에 re-parent). 커밋 메시지는 `git commit -F <file>`로(헤어 here-string 금지).

## 미션 / 전략
AGI 시대 개인 agent가 개인을 대신한다 → 검증된 agent 플랫폼. 경쟁(Moltbot/OpenClaw/Hermes)과 런타임으로 경쟁하지 않고, 그들이 OpenCanal 검증 노드가 되게 한다(R2 어댑터). 상세: docs/ROADMAP.md, 메모리 strategy-positioning.

## 베이스라인 (완료)
MVP 배포가능 + 11개 에이전트 테스트 통과. smoke: scripts/smoke.mjs(41) + apps/gateway/scripts/smoke2.mjs(10). 검증 루틴: `next build` + tsc(gateway/runner) + tsup + 두 smoke. 서버 재기동 시 prod는 `next build`→`next start`(dev가 .next를 덮으므로), 또는 preview_start(dev). DB 죽었으면 docker compose up -d.

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

### R3 — 학습 메모리 & 평판 v1
- [ ] 룸 결과/ContractReceipt를 OpenCrab에 ingest (러너 측, ocm_ 있을 때)
- [ ] 평판 v1: 응답률/승인률/이행률/분쟁률 계산 (현재 평판 v0 확장)
- [ ] 프로필 신뢰 신호 강화
- [ ] 검증: 스모크에 평판 케이스

### R4 — 말→성사 (Commerce Room)
- [ ] BotContract 이행 단계 (Offer/CounterOffer는 이미 trade 룸+Receipt로 일부; 조건표·이행상태 추가)
- [ ] 숙박/예약 vertical 최소형 (v1 계획서 Phase 4)
- [ ] can_spend off 유지, 승인 게이트 안에서 이행 기록
- [ ] 검증: 스모크

### R5 — 능력(skill) 생태계
- [ ] agent capability 모델 (승인 봉투 안)
- [ ] 어댑터 런타임 skill 매핑
- [ ] 검증

## 진행 메모
- (2026-06-13) 목표 v3 수립. R0부터 순서 진행. 외부 시크릿 필요 항목(R0 ocm_ 토큰, R1 텔레그램 봇 토큰)은 코드를 완성해두고 env로 주입 가능하게 만든 뒤, 시크릿 없이 가능한 데까지 검증.
