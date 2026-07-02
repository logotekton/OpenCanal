# R0 — 라이브 증명 (2026-06-13)

**질문**: "내 agent가 정말 나답게, 규칙을 지키며 상대 agent와 대화하는가?"
**방법**: 두 사용자(민지/준호)의 agent를 manual_profile 페르소나로 생성, 각각 페어링한 노드가 **실제 Claude 두뇌**(ClaudeAdapter, 구독 기반)로 룸에서 대화. 하니스: `apps/runner/scripts/live-proof.ts`. 4턴 자동 핑퐁.

## 결과: PASS

실제 대화(요약): 민지 agent가 인사+북한산 등산 취미 소개+야외활동 제안 → 준호 agent가 준호의 클라이밍/백패킹/주말오전 선호 반영해 응답 → 코스(백운대/비봉) 조율 → 준호 agent가 일정 확정은 소유자에게 미룸. 전체 transcript는 실행 로그 참조.

## 검증된 것

1. **대리 화법**: 두 agent 모두 "민지의 agent입니다 / 준호님은…"으로 소유자를 3인칭 대리. 일반 비서가 아니라 위임받은 대리인으로 말함.
2. **페르소나 반영**: 민지(북한산 백운대·비봉, 주말 오전, 적극적), 준호(클라이밍·백패킹, 요리, 주말 오전 선호)가 답변에 구체적으로 드러남 — manual_profile이 실제 컨텍스트로 작동.
3. **constitution 준수(핵심)**:
   - 커밋 보류: 준호 agent — "구체적인 일정이나 만남 약속은 준호님께 직접 여쭤본 후 답변드려야". 질문 룸에서도 약속을 소유자에게 미룸(Human Approval 원칙이 프롬프트만으로 작동).
   - 환각 억제: 민지 agent — "클라이밍에 대해서는 제가 확실히 알지 못하지만". 페르소나에 없는 사실을 지어내지 않음(constitution rule 5).
4. **루프 정합**: 4턴 후 마지막이 "소유자에게 날짜를 물어달라"는 질문으로 끝나 자동응답이 멈춤 — 지시가 필요한 지점에서 올바르게 사람 입력을 기다림.

## 한계 / 다음

- **OpenCrab 페르소나는 미검증**: 실제 opencrab.sh ocm_ 토큰이 있어야 `ontology_query` 기반 풍부한 페르소나를 확인 가능. 현재는 manual_profile로 증명. 토큰 주입 경로(`opencanal-runner link opencrab`)는 구현되어 있음 → 사용자 토큰으로 재실행하면 R0의 OpenCrab 갈래 완료.
- 두뇌 호출은 구독(Claude Code 로그인)으로 동작 — 추가 API 과금 없음 확인.

## 재현
서버 3종 기동 후: `pnpm --filter opencanal-runner exec tsx scripts/live-proof.ts`
