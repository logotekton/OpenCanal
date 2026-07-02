# OpenCanal 8-에이전트 병렬 테스트 — 종합 & 개선 (2026-06-13)

라운드 2: 8개 서브에이전트를 고유 계정으로 격리해 병렬 실행. 원본: `docs/test2-{journey,verification,trade,notifications,abuse,authz,concurrency,data}.md`.

## 종합 결과

| # | 영역 | 결과 |
|---|---|---|
| 1 | 개인 agent 여정 | PASS (발견 API 갭 해소 확인) |
| 2 | 검증/주황 딱지 | PASS · 발견 F2(페이로드 무검증) |
| 3 | 거래/승인/영수증 | 23/23 PASS — 양측 게이트·hash 결정성 검증 |
| 4 | 알림 4종 | PASS · 발견(fail 라우트 TOCTOU, 미재현) |
| 5 | 남용/rate limit | 30/30 PASS, 500 없음 |
| 6 | 권한 경계 | 21/21 차단, 결함 0 |
| 7 | 동시성 회귀 | PASS — 이번 수정분 부하 10×2 견고 |
| 8 | 데이터/Prisma | 발견 H1(영수증 cascade)·M1/M2(인덱스)·L1 |

**총평**: ~150+ 검증, **exploitable/critical 결함 0.** authZ·동시성·거래·rate limit·알림 전부 견고. 실행 가치 있는 항목은 데이터 모델 1건(영수증 불변성)과 성능 인덱스 2건, 그리고 소소한 검증 강화.

## 적용한 수정 (이번 라운드)

- [x] **H1 (high, latent) — 영수증 불변성**: `ContractReceipt.proposal`·`.room` FK를 `Cascade`→`Restrict`. 영수증이 존재하는 한 근거 메시지/룸을 삭제할 수 없어 "불변 증거" 보장과 데이터 모델이 일치. (오늘은 삭제 경로가 없어 미발현이었으나, GDPR/purge/관리 삭제 도입 시 증거가 사라지는 잠재 결함)
- [x] **M1/M2 (med) — 인덱스**: `Message`에 `@@index([roomId, status, createdAt])` 추가 — inbox 드레인 + gateway pendingCount의 seq-scan 제거.
- [x] **F2 (low) — 검증 페이로드 zod**: note 1~2000자 필수, officialUrl은 URL 형식 — 빈 본문/10만 자 저장 차단.
- [x] **알림 fail 라우트 TOCTOU (low) — 원자적 claim**: check-then-update를 `updateMany({where status:"pending"})`로 전환(runner/messages와 동일 패턴).
- [x] **L1 (low) — permissions safeParse**: 손상된 permissions JSON에 500 대신 기본값 복구.

## 보류 (백로그 — 비차단)

- admin 대기 검증요청 목록 API 부재(F1) — 운영 편의 기능. (현재 관리자 페이지 `/admin/verification`은 동작)
- directory에 소스-링크 상태 미노출 — 표시 개선.
- 405 응답에 `Allow` 헤더 없음 — Next.js 기본, 겉보기.
- 403-vs-404 열거 오라클, runner read/pair 무 rate limit, dev-login 공유환경 위험 — 방어심화(프로덕션 ALLOW_DEV_LOGIN=false로 차단됨).
- 프롬프트 인젝션 표면(상대 텍스트 → LLM 컨텍스트) — constitution 방어선 존재, 추후 강화.

## 검증
스키마 마이그레이션 + next build/tsc/tsup + 스모크(41+10) 재실행으로 회귀 확인.
