# 목표 v2: OpenCanal 깊이 개선 + 병렬 테스트 루프 (2026-06-12 시작)

> **세션이 끊겨도 이 파일을 읽고 이어서 작업한다.** (스케줄 태스크 `opencanal-goal-resume`가 5시간 주기로 재개)
> 작업 디렉토리: C:\Logotekton\OpenCanal · 서버: web :3000(preview), gateway :8787, postgres :5433(docker)
> 이전 목표(v1: 배포 준비+지시 구조+Tesla 디자인)는 완료됨 — git 없음, 문서가 유일한 기록.

## 미션

> AI native, AGI 시대가 오면 개인의 agent가 개인을 대신한다.
> 그 미래에 대비한 **검증된 agent 플랫폼**이 OpenCanal이다.

## 진행 방식 (사용자 지시)

1. 계획대로 개선 + refactoring 루프 → **배포 가능 단계를 객관 기준으로 판단**
2. 도달하면 **sub agent를 병렬로 띄워 OpenCanal 테스트**
3. 테스트 리뷰 → 개선점 도출 → 적용
4. 5시간 토큰 만료 시 resume 자동화로 계속

## 배포 가능 판단의 객관 기준 (Definition of Deployable) — ✅ 전 항목 충족 (2026-06-12)

- [x] D1. 빌드 전부 클린: next build ✓ + tsc(gateway/runner) ✓ + tsup ✓ + Docker 이미지 2종(web=0, gateway=0) ✓
- [x] D2. 스모크 전부 통과: smoke1 35개 + smoke2 10개 (production 빌드 기준)
- [x] D3. 알림 작동: 승인요청/지시실패/검증결과/거래확정 — 스모크 13단계에서 확인
- [x] D4. 권한 집행: trade는 L1+ & can_negotiate (스모크 9단계 "can_negotiate 없이 403" 확인)
- [x] D5. 남용 방어: rate limit(룸당 5/시간당 30), 룸 닫기, cross-user(자기 제안 확정 403, 타인 승인 403) 확인
- [x] D6. 합의의 기록: ContractReceipt + transcript hash + /receipts/:id (스모크 9단계)
- [x] D7. 평판 v0: 프로필 TRACK RECORD (메시지 수/승인률/확정 거래)

> 배포 시 주의: web은 standalone 빌드이므로 프로덕션 실행은 `node apps/web/.next/standalone/apps/web/server.js` (또는 Docker 이미지). `next start`는 경고와 함께 동작하지만 권장 아님.

## Phase 체크리스트

### Phase 1 — 실전 신뢰성 (D3, D4, D5)
- [ ] Notification 모델 + 마이그레이션 (userId, kind, title, href, readAt)
- [ ] 알림 생성 지점: 승인 요청 생성 시(소유자), 지시 실패 시(소유자), 검증 심사 결과(소유자), 거래 합의 확정(양측)
- [ ] 헤더 벨 + /notifications 페이지 (읽음 처리)
- [ ] agent 생성 시 L1 부여 (이메일 로그인 = 이메일 검증 완료이므로) — L0는 미인증 예약
- [ ] trade 룸 게이트: 양측 L1+ AND 개시 agent permissions.can_negotiate=true
- [ ] agent 설정에서 can_negotiate 토글 UI (소유자)
- [ ] 지시 rate limit: 룸당 pending 5개, 사용자당 시간당 30개
- [ ] 룸 닫기: PATCH /api/rooms/:id (참여 소유자) — closed 룸은 지시/메시지 거부
- [ ] 스모크 확장: 보안 케이스 (타인 룸 지시 403, 타인 승인 403, L0 trade 차단, rate limit, closed 룸)

### Phase 2 — 미션 실체화 (D6, D7)
- [ ] ContractReceipt 모델: roomId, proposalMessageId, acceptedByUserId, terms?, transcriptHash, createdAt
- [ ] trade 룸에서 승인되어 전달된 상대 agent 메시지에 "이 조건으로 확정" 버튼 (상대 소유자) → Receipt 생성 + 양측 알림 + 룸 system 메시지
- [ ] /receipts/:id 페이지 (양측 소유자만, transcript hash 표시)
- [ ] 평판 v0: 프로필에 응답 수 / 승인률 / 확정 거래 수 (쿼리 계산, 모델 추가 없이)
- [ ] 스모크: Receipt 생성/조회/권한

### Phase 3 — Refactoring 루프 (D1, D2)
- [ ] API 라우트 공통 패턴 추출 (auth 가드, 에러 응답) — 중복 제거
- [ ] /simplify 수준 자체 점검: 죽은 코드, 단순화 가능 지점
- [ ] 전체 빌드 + 전체 스모크 + Docker 재빌드 → D1~D7 체크
- [ ] GOAL_PROGRESS.md의 Definition of Deployable 전 항목 체크 → "배포 가능" 선언

### Phase 4 — Sub-agent 병렬 테스트 (배포 가능 도달 후) — 실행 중
- [~] 테스트 에이전트 A (사용자 여정) → docs/test-journey.md (병렬 실행 중)
- [~] 테스트 에이전트 B (보안/남용) → docs/test-security.md (병렬 실행 중)
- [~] 테스트 에이전트 C (코드 리뷰) → docs/test-codereview.md (병렬 실행 중)
- [ ] 결과를 docs/TEST_REVIEW.md로 수합

**선제 확인된 버그 (Phase 5에서 수정):**
- TOCTOU @ apps/web/src/app/api/runner/messages/route.ts:49-89 — instruction status 체크와 update 사이 갭. WS push + inbox 드레인 동시 유입 시 같은 지시로 메시지 중복 생성 가능. 수정: updateMany({where:{id,status:"pending"}})로 원자적 claim 후 count===1일 때만 메시지 생성.

### Phase 5 — 리뷰 & 개선 — ✅ 완료
- [x] TEST_REVIEW.md 수합 → 우선순위화 (보안 57/57 PASS, 코드리뷰 high 5 + TOCTOU, 여정 P0)
- [x] 핵심 개선 9건(F1~F9) 적용 + 재검증: build/tsc/tsup/Docker 클린, smoke 39+10 통과
- [x] 최종 요약 + 메모리 갱신

## 최종 결과 (2026-06-12)

목표 v2 완수. OpenCanal은 **배포 가능 단계** 도달 + 병렬 테스트 검증 + 발견된 결함 수정 완료.

- 보안: 블랙박스 57/57 통과, 0 finding
- 코드리뷰 high 5건 전부 수정: codex RCE(stdin+shell:false), 지시 TOCTOU(원자적 claim), inReplyToId 멱등성/검증, 게이트웨이 시크릿(timingSafeEqual+prod throw)
- 여정 P0(발견 API) + SHOULD 3건(receipt race/hash, attest zod) 수정
- 회귀 스모크 49개(39+10) 통과, Docker 이미지 2종 빌드

남은 백로그(비차단): H5 응답자 게이트(승인으로 실질 보호), admin 검증요청 목록 API(P1), 승인대기 목록 API(P2), 프롬프트 인젝션 강화, receipt 멀티참여 룸 대비.

## 진행 메모

- (2026-06-12) 목표 v2 수립. 방향 재검토 결론: 구조 유지, "검증의 집행"과 "합의의 기록"을 보강.
- (2026-06-12) Phase 1 완료: Notification 모델+벨+페이지, 알림 4지점(승인요청/지시실패/검증결과/거래확정), agent 생성 시 L1, trade 게이트(L1+ & can_negotiate), 권한 토글 UI, 지시 rate limit(룸당 5/시간당 30), 룸 닫기.
- (2026-06-12) Phase 2 완료: ContractReceipt(transcript hash), "이 조건으로 확정" 버튼, /receipts/:id, 프로필 평판 v0(메시지 수/승인률/확정 거래).
- (2026-06-12) Phase 3: agent-loop 공통 파이프라인(compose) 추출, 동적 import 제거. 검증 — smoke1 35개 + smoke2 10개 통과(production 빌드 기준), next build/tsc/tsup 클린, web Docker 빌드 성공. gateway Docker 빌드 진행 중.
  - 상태 규칙(중요): trade 룸 거래 확정은 approval="approved"인 상대 agent 메시지에만 가능. Receipt 생성 시 transcript hash = 확정 시점까지 전달된(approval in none|approved) 메시지들의 SHA-256.
