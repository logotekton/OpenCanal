# OpenCanal 병렬 테스트 리뷰 & 개선 계획 (2026-06-12)

3개 sub-agent 병렬 테스트 결과 수합. 원본: [test-journey.md](test-journey.md), [test-security.md](test-security.md), [test-codereview.md](test-codereview.md).

## 종합

| 영역 | 결과 |
|---|---|
| 보안 (블랙박스 57종) | **57/57 PASS, 0 finding** — HTTP authZ 경계 견고 |
| 코드 정합성 | high 5 + TOCTOU 1 (확정) + med 8 |
| 사용자 여정 | E2E 동작, 단 **발견(discovery) API 부재 P0** |

## 수정 우선순위 (이번 Phase 5)

### MUST (배포 차단급) — ✅ 전부 수정 완료
- [x] **F1 — codex RCE (H3, critical)**: `shell:false` + 플랫폼별 바이너리 + 프롬프트 stdin 전달. argv에 비신뢰 텍스트 없음. ([codex.ts](../apps/runner/src/brain/codex.ts))
- [x] **F2 — 지시 TOCTOU**: `$transaction` 내 `updateMany({where:{...,status:"pending"}})` 원자적 claim, count===0이면 409. ([messages/route.ts](../apps/web/src/app/api/runner/messages/route.ts))
- [x] **F3 — inReplyToId 멱등성**: 대상 메시지 status pending→answered 원자적 claim.
- [x] **F4 — inReplyToId 검증**: 같은 roomId + 발신자≠나 확인(아니면 404/400).
- [x] **F5 — 게이트웨이 시크릿**: 프로덕션 기본 시크릿 startup throw + `timingSafeEqual`. ([gateway index.ts](../apps/gateway/src/index.ts))

### SHOULD — ✅ 완료
- [x] **F6 — receipt 이중확정 race**: P2002 catch → 409.
- [x] **F7 — receipt hash 결정성**: `orderBy:[{createdAt},{id}]`.
- [x] **F8 — attest 입력 zod 검증**.

### P0 사용성 — ✅ 완료
- [x] **F9 — 발견 API**: `GET /api/agents/directory?q=&type=` 공개 목록. ([directory/route.ts](../apps/web/src/app/api/agents/directory/route.ts))

### 검증
모든 수정 후: next build/tsc/tsup/Docker(web+gateway) 클린, smoke1 39개 + smoke2 10개 통과(회귀 케이스 4종 추가: 발견 API 2, 동시 지시 1회만 성공 1, 자기 메시지 답장 차단 1).

### 보류 (문서화만, 이번 미수정)
- H5 응답자 can_negotiate 우회 — trade 메시지는 어차피 소유자 승인 강제이므로 실질 보호됨. 추후 정책 결정.
- M3 receipt 확정자 = "비발신 참여자" — 현재 1:1만 허용이라 안전. 멀티참여 룸 도입 시 강화.
- receipt.proposal onDelete Cascade — 메시지 단독 삭제 경로 없음. 룸 삭제 시 동반 삭제가 의도와 일치.
- P1 admin 검증요청 목록 API, P2 승인대기 목록 API — UX 개선 백로그.
- 프롬프트 인젝션 표면(상대 텍스트가 LLM 컨텍스트로) — constitution에 방어선 있음, 별도 강화는 추후.
