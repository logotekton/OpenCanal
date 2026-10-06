# CHANGE-002 — Oracle v.3: 창발 판정 빈틈 막기, INTERNAL 코드 계약화

- 연결: Oracle v2026-10-06.3, TASK-001, RISK-001 F10
- 작성: 플래너(Oracle 소유자 대리). 순서는 Oracle → 테스트 → 구현이다.

## 무엇이 문제였나

- v.2 §4는 엣지의 "유효 출처"에 엣지에 직접 적은 출처를 포함했다.
- 그래서 같은 주인(A)의 두 노드를 잇는 엣지에 C의 노드 출처 하나만 붙여도 "창발 엣지"로 세졌고, L1을 통과했다. 의미 없는 델타브레인이 품질 하한을 통과하는 경로였다.
- 서비스가 내부 오류에 `INTERNAL` 코드를 돌려주는데 `ErrorCode`에는 없었다 (통합 단계 보고).

## 바꾼 것

| 단계 | 파일 | 내용 |
|---|---|---|
| Oracle | `docs/oracle/ORACLE_MANIFEST.md` | v.3. 창발·호스트 판정은 양 끝 노드의 출처로만 한다. 엣지 직접 출처는 근거로 유효성만 검사한다. MUST-Q5 엣지 조항을 모든 source–source 엣지로 확대한다. `ErrorCode.INTERNAL`을 추가한다. 모두 §9 플래너 추가에 기록 |
| 계약 | `src/opencanal/models.py` | `ErrorCode.INTERNAL` |
| 테스트 | `tests/oracle/test_oracle_validator.py` | v.3 테스트 3개를 추가했다. size 테스트의 채움 엣지는 질의 노드에 붙이도록 바꿨다 (채움이 Q5를 건드리지 않게) |
| 구현 | `src/opencanal/validator.py` | `_analyze_edges`는 양 끝 노드의 출처만 쓴다. `_check_novelty`는 모든 source–source 엣지에 적용한다 |
| 구현 | `src/opencanal/service.py` | `INTERNAL_CODE = ErrorCode.INTERNAL.value` |
| 단위 테스트 | `tests/unit/test_unit_validator.py` | 예전 규칙을 고정하던 테스트를 v.3 규칙에 맞췄다. 샘플의 복사 엣지를 맥락 엣지(q→sa2)로 바꿨고, 홉 거리 테스트는 같은 거리를 유지하도록 재구성했다 |

## 빨강 → 초록

1. v.3 테스트를 추가하고 구현을 바꾸기 전: `1 failed, 2 passed` (`test_must_q3_v3_edge_level_ref_does_not_create_emergence` — 빈틈 재현)
2. 구현을 바꾼 직후: `27 failed, 493 passed` — 예전 규칙에 기대던 단위 테스트 샘플(복사 엣지 `e_copy`)과 size 채움 엣지, 그리고 내가 쓴 v.3 테스트의 노드 선택(a-n3→a-n2는 입력 엣지라 NOT_NOVEL이 같이 남)이 원인
3. 테스트 데이터를 고친 뒤: `.venv/bin/python -m pytest -q -p no:cacheprovider` → **520 passed**

## 남은 확인

- §9의 v.3 항목 3개는 오너 확인 대기다.
- good-01의 창발 엣지 8개와 호스트 엣지 7개는 바뀌지 않았다 (`test_must_q3_v3_good01_unchanged`).
