# CHANGE-007 — Oracle v.8 통합 기록 (다리 단위 평가, 창발 재정의, 평가 단위마다 설명, 현실 제약 필드)

> NDSH 부록 B-7 양식. 통합 담당(Integrator)이 2026-10-07에 남긴 기록이다. 사실만 적는다.
> 기준 문서는 `docs/oracle/ORACLE_MANIFEST.md` v2026-10-07.8이다. 그중 §2 오너 결정(2026-10-07 행 3개), §4 다리·창발 정의, MUST-Q3·Q4·Q7, HUMAN-01, §9 "(v.8)" 행, §10을 따른다. 계약 변경(`DeltaNode.constraints`, `DeltabrainStats.bridge_node_ids`·`host_bridge_node_ids`·`bridges_with_constraints`, `ErrorCode.NOT_RATEABLE`, `EdgeRating.edge_id` = 평가 대상 ID)은 이미 `models.py`와 TASK-001 §5에 커밋되어 있다.
> 기준 커밋은 `fdb0368`이다. 지금 HEAD `cbeeb06`은 여기에 `evidence/L3-001.md` 한 파일만 더한 커밋이라 코드와 테스트는 같다. 이번 작업은 커밋하지 않았다.
> 작업 파일 위치: `$V`는 이 세션 scratchpad의 `v8/`, `$I`는 `$V/integ/`, `$LLM`은 같은 scratchpad의 `llm/`(HUMAN-001 합성·평가 데이터, 커밋 안 함)다. 모두 저장소 밖에 있다. 기준선 worktree는 `$V/integ-base`에 만들었다가 지웠다(`git worktree list`에는 본 작업 트리 하나만 있다).

## 1. v.8을 왜 바꿨나 — 오너 결정 3건과 HUMAN-001

v.7까지는 "주인 2명 이상을 인용한 엣지"가 모두 창발 엣지였고, 사람 평가 단위도 엣지였다. 첫 LLM 합성 6건(HUMAN-001)에서 두 정의가 모두 실제 데이터와 맞지 않았다.

- **창발 판정이 너무 쉬웠다.** 다리(주인 2명 이상을 인용한 `new` 노드)에 닿는 엣지는 질의 노드로 가는 엣지든, 그 다리가 스스로 인용한 출처로 가는 엣지든 모두 창발로 셌다. 6건의 엣지 114개 중 113개가 v.7 창발 엣지였다(§7 표). 합성 에이전트 6개가 모두 이 점을 지적했다(§10 "창발 판정이 구조적으로 너무 쉽다" 행).
- **오너는 다리 단위로 판단했다.** 오너는 다리 26개를 평가했고, 엣지는 그 다리의 설명으로 읽었다. 같은 평가를 엣지 단위로 옮기면 품질이 합성기가 그린 엣지 수에 따라 흔들렸다(R1 다리 기준 0.40, 엣지 기준 0.28. HUMAN-001 §2).
- **같은 개념도 서술의 구체성에 따라 0/0/0~1/1/1로 갈렸다**(HUMAN-001 §3.3). 설명이 없는 단위는 평가할 수 없다.
- **허구의 먼 분야 유추는 현장 제약에서 무너졌다**(F 커널: 타당성 9/12, 쓸모 4/12, 세 축 모두 "예" 0). 오너 메모는 모두 제작 공수, 반송 비용, 제작 효율 같은 현실 제약이었고, 합성 프로토콜은 이것을 따지라고 요구하지 않았다.

오너 결정 3건(§2, 2026-10-07)과 반영:

| 오너 결정 | 오너 답 | v.8 반영 | 코드 반영 |
|---|---|---|---|
| 합성 프로토콜에 현실 제약 검토 | 넣는다 | 다리 노드의 `constraints` 필드. 프로토콜이 요구하지만 L1 거부 사유는 아니다. 채운 수를 `bridges_with_constraints`로 보고한다 (§9 v.8) | `protocol.py` 13번 단계·규칙 문구, `validator.py`·`store.py` 통계 |
| 평가 단위와 창발 판정 | 둘 다 바꾼다 | §4 다리·호스트 다리·창발 엣지(질의 엣지·자기 앵커 엣지 제외, `new`–`new` 포함) 재정의, MUST-Q3(다리 ∪ 창발 엣지), MUST-Q4(다리 `summary` 40~600자), MUST-Q7(다리 요약 + 창발 rationale), HUMAN-01(평가 단위 = 다리 노드 ∪ 창발 엣지), `deltabrain_rate`의 `target_id`·`NOT_RATEABLE` | `validator.py`, `store.py`, `service.py`, `protocol.py` |
| 보류한 자동 품질 검사 | 넣지 않고 LLM 심사로 | §10 결정. L3 실험 시작(evidence/L3-001.md) | 없음. L1에 새 휴리스틱을 넣지 않았다 |

## 2. 변경 요약

병렬 단계에서는 네 명이 작업했다.

- **테스트 작성자(Oracle 쪽, 구현과 독립)**: `tests/oracle/_v8.py`(§4 v.8 독립 참조 구현), `test_oracle_v8_validator.py`(35개), `test_oracle_v8_service.py`(107개)를 새로 만들었다. 기존 oracle 파일 9개를 v.8에 맞게 고쳤다(§6). 새 golden `fixtures/deltabrains/bad-templated-02.json`을 더했다(기존 fixture는 고치지 않음).
- **Builder — 검증기**: `validator.py`, `test_unit_validator.py`, 새 `test_unit_validator_v8.py`(35개).
  - 다리 = 유효 출처의 주인이 2명 이상인 `new` 노드. 호스트 다리 = 그중 호스트 서브브레인을 인용하는 것.
  - 창발 엣지 = 주인 2명 이상, 질의 노드에 닿지 않음, 자기 앵커 아님. 자기 앵커는 `new` N ↔ `source` S(방향 무관)이고 S가 인용한 (subbrain_id, version, node_id)가 이미 N의 출처에 있는 경우다. `new`–`new` 엣지는 창발로 센다.
  - MUST-Q3은 다리 ∪ 창발 엣지 기준이다. MUST-Q4에서 다리 `summary`는 정규화 후 40~600자이고, 어기면 `node_id`가 붙은 `RATIONALE_MISSING`이다. MUST-Q7은 다리 요약과 창발 rationale을 한 묶음으로 비교하고, 20% 기준은 정확한 분수로 비교한다.
  - 통계 `bridge_node_ids`·`host_bridge_node_ids`·`bridges_with_constraints`를 채운다.
- **Builder — 서비스·저장소**: `store.py`, `service.py`와 단위 테스트 4개 파일.
  - `deltabrain_rate`는 `target_id`를 받는다. 예전 인자 `edge_id`는 `INVALID_ARGUMENT`다.
  - 평가 가능 여부는 보는 사람의 통계(다리 ∪ 창발 엣지)로 판정한다.
  - `rating_summary`·`ratings.units`는 평가 단위 기준이다. 품질 = 평가된 단위 중 모든 평가가 1/1/1인 단위의 비율이다.
  - 보는 사람 기준 통계(`_stats_over_keys`)를 v.8 규칙으로 다시 계산한다. v.8 이전에 저장된 레코드도 v.8 규칙으로 다시 계산해 보여준다.
- **Builder — 프로토콜**: `protocol.py`, `test_unit_protocol.py`(독스트링), 새 `test_unit_protocol_v8.py`(30개).
  - 단계는 15개에서 16개가 됐다. 다리 정의, 창발 엣지 세 조건, 맥락 엣지, 요약 40~600자, `constraints`(13번 단계), 평가 단위를 넣었다.
  - 예시 제출물에 실제 창발 엣지(e3)를 넣었다. 예전 예시는 v.8 기준으로 창발 엣지가 0개였다.

### 2.1 통합 단계에서 직접 바꾼 것

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/opencanal/service.py` `_deltabrain_rate` | 뷰에 없는 `target_id`를 `NOT_FOUND`로 돌려주던 분기(`known` 집합)를 지웠다. 이제 보는 사람의 평가 단위가 아닌 ID는 모르는 ID까지 모두 `NOT_RATEABLE`이다. 주석도 같은 뜻으로 고쳤다 | §9 (v.8) "대상 = 다리 노드 또는 창발 엣지 (`target_id`), 아니면 `NOT_RATEABLE`", `models.ErrorCode.NOT_RATEABLE` 주석 "target is neither a bridge node nor an emergent edge". TASK §5의 `NOT_FOUND`는 델타브레인 자체(비참여자, NEVER-05)에 이미 쓰인다. 통합을 시작할 때 남은 실패 1건(`test_v8_rate_unknown_target_in_a_visible_deltabrain_is_not_rateable`)이 이것이었다 |
| `tests/unit/test_unit_service.py` 단언 2곳 | `test_deltabrain_rate_get_list`의 `target_id="zzz"`, `test_deltabrain_get_and_rate_use_the_viewers_stats_not_the_stored_ones`의 `"nope"`: `NOT_FOUND` → `NOT_RATEABLE` | 위와 같다 |
| `tests/unit/test_unit_integration.py` 단언 1곳 | 두 세계 비교의 `rate_unknown`(e99): `NOT_FOUND` → `NOT_RATEABLE` | 위와 같다. 두 세계에서 응답이 같은지 보는 비교는 그대로 통과한다 |
| `evidence/CHANGE-007.md` (신규) | 이 문서 | |

NEVER-11은 영향받지 않는다. 판정은 여전히 보는 사람 뷰의 통계만 쓰고, 오류 종류는 하나 줄었다(모르는 ID와 평가 단위가 아닌 ID가 같은 코드). 두 세계 비교 테스트(`test_oracle_v4_exposure.py`의 `rate_unknown_edge`, `test_oracle_v8_service.py` NEVER-11 60개, `test_unit_integration.py`)가 모두 초록이다.

고정 파일(`docs/`, `config/`, 기존 `fixtures/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. `git diff HEAD --stat -- docs config fixtures src/opencanal/models.py src/opencanal/textnorm.py src/opencanal/config.py pyproject.toml`의 출력은 비어 있다. `fixtures/deltabrains/bad-templated-02.json`은 테스트 작성자가 새로 만든 미추적 파일이다. §6.4 표에 행이 없으므로 오너 검토가 필요하다(§8).

## 3. 실행 명령

```bash
# 자동 검사 (저장소 루트)
umask 022; .venv/bin/python -m pytest -q -p no:cacheprovider
for s in 0 1 12345; do PYTHONHASHSEED=$s .venv/bin/python -m pytest -q -p no:cacheprovider; done

# 빨강 기준선 (저장소 밖 worktree)
git worktree add --detach $V/integ-base fdb0368
rm -rf $V/integ-base/tests/oracle && cp -R tests/oracle $V/integ-base/tests/oracle   # __pycache__ 제거
cp fixtures/deltabrains/bad-templated-02.json $V/integ-base/fixtures/deltabrains/
cd $V/integ-base && export PYTHONPATH=$V/integ-base/src && umask 022
<repo>/.venv/bin/python -m pytest -q -p no:cacheprovider tests/oracle -rfE   # (b) 출력 $V/integ-red-oracle.txt
<repo>/.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit          # (a') 기준선 자체 단위 테스트
git worktree remove --force $V/integ-base && git worktree prune

# (a) 커밋된 테스트 그대로: git archive fdb0368 | tar -x -C $I/base-archive (끝난 뒤 지움)
# 실제 델타브레인 6건: .venv/bin/python $I/regress6.py > $I/regress6.json
# 독립 참조 구현 대조:  .venv/bin/python $I/xcheck.py   (tests/oracle/_v8.analyse)
```

참고 사항.
- **import 경로.** 두 기준선 모두 `opencanal.__file__`이 worktree(또는 archive)의 `src`를 가리키는 것을 확인했다.
- **fixture 복사.** `test_oracle_fixtures.py`의 파싱 목록이 `bad-templated-02.json`을 읽는다. 복사하지 않으면 FileNotFoundError가 나는데, 이것은 v.8과 무관한 기준선 부산물이라 함께 복사했다.
- **`git stash`는 쓰지 않았다.** 실행 전후 `git stash list`는 비어 있었다.

## 4. 빨강 기준선

| 실행 | 결과 | 해석 |
|---|---|---|
| (a) `fdb0368` 그대로 (커밋된 테스트) | oracle **773 passed**, unit **2 failed, 882 passed** | v.8은 매니페스트·`models.py`·TASK에만 있었다. 단위 2건은 작업 지시의 기준선과 같다(`test_unit_store.py::test_viewer_stats_do_not_reveal_who_a_masked_contributor_is[user_b/user_f]`, 보는 사람 통계에 v.8 필드가 없음) |
| (b) (a)에 작업 트리의 `tests/oracle/` 전체와 `bad-templated-02.json` (oracle 919개) | **70 failed, 108 errors, 741 passed** | 아래 표. 모두 v.8 변경 때문이다 |

(b) 파일별 내역 (`$V/integ-red-oracle.txt`):

| 파일 | failed | errors | 원인 |
|---|---|---|---|
| `test_oracle_v8_validator.py` (신규 35) | 24 | 0 | 다리·호스트 다리 통계 없음, 질의·자기 앵커 엣지를 창발로 셈, 다리 `summary` 검사 없음, MUST-Q7 단위가 다름, `constraints` 집계 없음 |
| `test_oracle_v8_service.py` (신규 107) | 36 | 69 | `deltabrain_rate`가 `target_id`를 모름(`INVALID_ARGUMENT`), `NOT_RATEABLE` 없음, v.8 통계·품질·프로토콜 `constraints` 없음. errors 69는 NEVER-11 두 세계 fixture(`rich_delta`)가 v.7 검증기에서 `RATIONALE_MISSING`(자기 앵커 엣지 e13, 질의 엣지 e14에 rationale 없음. v.7에서는 둘 다 창발 엣지였다)으로 거부되어 생겼다 |
| `test_oracle_validator.py` | 5 | 0 | good-01 통계·`compute_stats`·v3 good-01 창발 집합이 v.7 값({e3..e10}), 20% 경계 10단위, `test_must_q7_templated_rationale`가 XPASS(strict) |
| `test_oracle_v4_validator.py` | 2 | 0 | 엣지에 적은 호스트 출처 테스트의 창발 집합 {e3}·다리, 10단위 중 2개 같음 |
| `test_oracle_flow.py`, `test_oracle_exposure.py`, `test_oracle_v4_untrusted.py` | 1 + 1 + 1 | 0 | 평가 호출이 `target_id`, 기대 코드 `NOT_RATEABLE` |
| `test_oracle_v4_exposure.py` | 0 | 17 | NEVER-11 두 세계 fixture가 `target_id`로 평가하고 v.8 창발 집합을 단언한다 |
| `test_oracle_v4_untrusted.py` | 0 | 5 | q01_flow fixture의 평가 호출이 `target_id`를 쓴다 |
| `test_oracle_v5_unlinkability.py` | 0 | 17 | `_collect`의 평가 호출이 `target_id`를 쓰고 `rate_e3/e9/n2`가 ok여야 한다 |

테스트 작성자가 보고한 숫자(71 failed, 108 errors)와 failed가 하나 다르다. 테스트 작성자는 src와 config만 scratch에 복사해 돌려서 `test_oracle_crypto.py::test_must_e1_key_location_is_gitignored`가 경로 때문에 실패했다. 이 기록의 worktree에서는 `.gitignore`가 있어 이 테스트가 통과한다. 그 밖의 빨강 목록은 테스트 작성자 보고의 원인 분류와 같다. 통합 전 작업 트리에서는 **1 failed, 1873 passed, 1 xfailed**였다(§2.1의 `NOT_RATEABLE` 1건).

## 5. 초록 결과

- 전체 **1874 passed, 1 xfailed** (약 18초, `umask 022`). oracle 918 + xfail 1, unit 956이다. `PYTHONHASHSEED` 0, 1, 12345로 세 번 더 돌려도 같았다.
- xfail 1건은 의도된 것이다. `test_oracle_validator.py::test_must_q7_templated_rationale`(strict)이고, `bad-templated.json`이 v.8에서 수락되기 때문이다(§8.2). 자기 앵커 엣지를 아직 세는 구현이면 XPASS가 나서 실패한다.
- 기준 1657개(oracle 773 + unit 884)에서 1875개로 218개가 늘었다:

| 파일 | 기준 `fdb0368` | 지금 | 차이 |
|---|---|---|---|
| `test_oracle_v8_service.py` (신규) | 0 | 107 | +107 |
| `test_oracle_v8_validator.py` (신규) | 0 | 35 | +35 |
| `test_oracle_fixtures.py` | 37 | 39 | +2 (`bad-templated-02` 파싱, 틀 문장이 평가 단위 밖에 있음을 손으로 고정) |
| `test_oracle_v4_exposure.py` | 21 | 23 | +2 (두 세계 비교가 빈 비교가 아님을 확인) |
| `test_unit_validator_v8.py` (신규) | 0 | 35 | +35 |
| `test_unit_protocol_v8.py` (신규) | 0 | 30 | +30 |
| `test_unit_store.py` | 54 | 59 | +5 |
| `test_unit_validator.py` | 71 | 73 | +2 |
| 그 밖의 파일 | — | — | 개수는 같다 |

## 6. 바뀐 기존 테스트와 근거 Oracle 줄

oracle 쪽은 테스트 작성자가, unit 쪽은 Builder가 바꿨다(unit 3곳은 통합 담당, §2.1). 통합 담당은 세 가지를 확인했다. 근거 줄이 매니페스트 v.8에 있다는 것, `git diff HEAD`의 단언이 아래 설명과 맞는다는 것, 그리고 "기준선" 열의 결과(§4 (b))다.

| 테스트 | 바뀐 것 | 근거 Oracle 줄 | 기준선 |
|---|---|---|---|
| `test_oracle_fixtures.py::test_fixture_good01_satisfies_every_l1_rule_by_hand` | 손 계산을 v.8로 바꿨다. 다리 {n1,n2}(둘 다 호스트 다리), 질의 엣지 {e1,e2}, 자기 앵커 {e5..e8}, 창발 {e3,e4,e9,e10}, 호스트에 닿는 창발 {e3,e4,e10}, 다리 요약 40~600자. 파싱 목록에 `bad-templated-02` 추가 | §4 다리·창발 엣지 (v.8), MUST-Q4 v.8 | 초록 (손 계산, 구현 무관) |
| `test_oracle_fixtures.py::test_fixture_v8_bad_templated_template_sits_on_non_unit_edges` (신규) | `bad-templated.json`의 틀 문장이 e5·e6·e7(자기 앵커)과 e10에만 있어 평가 단위 6개 중 중복 0개임을 손으로 고정 | §6.4 대 MUST-Q7 v.8 충돌 (§8.2) | 초록 |
| `test_oracle_flow.py::test_flow_q01_import_publish_open_submit_read_rate` | GOOD_EMERGENT v.8과 다리 ID. `edge_id` → `target_id`, `NOT_EMERGENT_EDGE` → `NOT_RATEABLE`, 다리 n1 평가 허용 | §9 (v.8) `deltabrain_rate` 행, TASK §5 | 빨강 |
| `test_oracle_validator.py` (good01·compute_stats·v3 good01) | GOOD_EMERGENT·GOOD_HOST_TOUCHING을 v.8로, good01 통계에 다리 ID와 `bridges_with_constraints` 0 | §4 (v.8) | 빨강 ×3 |
| `…::test_must_q3_member_only_bridges_are_host_not_touched` | `RATIONALE_MISSING`을 허용 코드로 더함(n-bc 요약이 짧음) | MUST-Q4 v.8 | 초록 |
| `…::test_must_q7_templated_rationale` | strict xfail로 바꿈 | §6.4 대 MUST-Q7 v.8 (§8.2) | 빨강 (XPASS) |
| `…::test_must_q7_duplicate_share_at_twenty_percent_is_allowed` | `mut_templated_at_limit`를 정확히 10단위로 다시 만듦(e12 = e3 문장) | MUST-Q7 v.8 평가 단위 | 빨강 |
| `test_oracle_v4_validator.py::test_must_q3_v3_edge_level_host_ref_does_not_touch_host` | 창발 {e3}, 다리 n-bc, `RATIONALE_MISSING` 허용 | §4 v.8 자기 앵커, MUST-Q4 v.8 | 빨강 |
| `…` 10단위 테스트와 라벨 틀 테스트 | `ten_emergent` → `ten_units`(다리 2 + 창발 엣지 8). 라벨 틀 테스트는 e7 대신 e10을 씀(e7은 v.8에서 자기 앵커) | MUST-Q7 v.8 | 빨강 1 (`two_of_ten`) |
| `test_oracle_v4_gaps.py::test_must_q7_v4_templated_share_counts_emergent_edges_only` | 단위 집합을 v.8로(비단위 e1,e2,e5..e8은 비율을 묽히지 않음, 2/6) | MUST-Q7 v.8 | 초록 |
| `test_oracle_v4_exposure.py` NEVER-11 두 세계 | 실제 창발 집합 v.8(distinct {e3,e4,e9,e10}, same {e3,e4,e10}), 모든 노드·엣지 ID를 `target_id`로 평가. 신규 `test_never_11_v8_viewer_stats_carry_v8_fields_and_ratings_succeed`로 빈 비교 방지 | §9 (v.8), TASK §5, NEVER-11 | 오류 17 |
| `test_oracle_v5_unlinkability.py::_collect` | 평가 호출이 `target_id`. `rate_n2`(다리)와 `rate_e5`(자기 앵커) 추가, `rate_e3/e9/n2` ok 단언 | TASK §5 (v.8) | 오류 17 |
| `test_oracle_exposure.py::test_never_05_non_participant_gets_not_found_for_canal_and_deltabrain` | 평가 호출이 `target_id` | TASK §5 (v.8) | 빨강 |
| `test_oracle_v4_untrusted.py` | 자유 응답 훑기의 평가 호출이 `target_id`. 다리 평가 경로와 자기 앵커 `NOT_RATEABLE` 경로 추가, 기대 코드 `NOT_EMERGENT_EDGE` → `NOT_RATEABLE` | §9 (v.8), TASK §5 | 빨강 1, 오류 5 |
| `tests/unit/test_unit_validator.py` | VALID의 n1에 요약을 붙이고, e3가 sa1을 가리키게 하고, 자기 앵커 e_anchor를 더함. 크기 한도·먼 노드·"메시지대로 고치면 통과" 테스트를 v.8로 | §4, MUST-Q3·Q4 v.8 | — |
| `tests/unit/test_unit_store.py` | 기준선 실패 2건: `_same_owner_world`에 다리 nbb(같은 주인 세계에서는 다리 아님), 호스트 다리 nab, 자기 앵커 e3, 질의 엣지 eq를 더해 두 세계의 v.8 통계가 같은지 본다. 신규 5개: 가린 호스트는 호스트 다리가 아님, v.8 이전 레코드 재계산, 검증기 `compute_stats`와 일치 | NEVER-11 v.4, §4 v.8 | 빨강 2 (§4 (a)) |
| `tests/unit/test_unit_service.py` | `target_id`, `NOT_RATEABLE`(질의 노드·비창발 엣지·뷰에서 다리 아님·모르는 ID), `edge_id` 거부, 다리 평가와 품질, `rating_summary` 키 | §9 (v.8), HUMAN-01 v.8 | — |
| `tests/unit/test_unit_integration.py`, `test_unit_never11_v5.py` | `edge_id` → `target_id`, good-01 v.8 값, 같은 주인 다리 n-bb 두 세계 비교, e1·e5·s-b2·e99 `NOT_RATEABLE`. never11_v5는 다리와 창발 엣지를 모두 평가 | §9 (v.8), NEVER-11 | — |
| `tests/unit/test_unit_protocol.py` | 독스트링만 | — | — |

**Oracle과 어긋나는 oracle 테스트는 찾지 못했다.** 919개 중 918개가 초록이고, 나머지 1개는 Oracle 안의 충돌(§6.4 대 MUST-Q7 v.8)을 표시하는 strict xfail이다. 통합을 시작할 때 실패하던 1건(`NOT_RATEABLE`)은 Oracle 문장 그대로였으므로 테스트가 아니라 src를 고쳤다(§2.1).

## 7. 실제 델타브레인 6건 v.8 재검증

HUMAN-001의 6건(`$LLM/runs/<run>/attempt1.json`)을 작업 트리의 `validator.validate_deltabrain`으로 다시 검증했다. 6건은 v.7에서 합성·제출된 것이다. 파일은 읽기만 했다.

- **컨텍스트**: `canal_F.json`·`canal_R.json`의 `untrusted_data.host`와 `untrusted_data.subbrains`로 `CanalContext`를 다시 만들었다.
- **주인 ID**: 호스트는 `"HOST"`, 멤버는 `owner_display` 문자열이다. 커널마다 서로 다른 것을 확인했다.
- **설정**: 금지 일반어와 조사 설정은 서비스와 같은 `load_config`로 읽었다.
- **대조**: 같은 6건을 `tests/oracle/_v8.analyse`(독립 참조 구현)로도 계산했다. 다리·호스트 다리·창발·호스트에 닿는 창발 집합이 6건 모두 한 원소도 다르지 않다.

| 실행 | 노드/엣지 | v.7 창발 (호스트) | v.8 결과 | 다리 | 호스트 다리 | v.8 창발 엣지 (호스트에 닿음) | 빠진 엣지: 질의 / 자기 앵커 | 평가 단위 | `bridges_with_constraints` | 다리 요약 길이(정규화) |
|---|---|---|---|---|---|---|---|---|---|---|
| F1 | 20 / 20 | 20 (20) | **수락**, 위반 없음 | 4 | 4 | 6 (6): e4 e5 e6 e7 e12 e17 | 4 / 10 | 10 | 0 | 97~135 |
| F2 | 18 / 17 | 17 (17) | **수락**, 위반 없음 | 4 | 4 | 3 (3): e4 e5 e13 | 4 / 10 | 7 | 0 | 105~151 |
| F3 | 17 / 18 | 18 (18) | **수락**, 위반 없음 | 4 | 4 | 7 (7): E5 E9 E10 E12 E13 E17 E18 | 3 / 8 | 11 | 0 | 74~115 |
| R1 | 17 / 19 | 19 (19) | **수락**, 위반 없음 | 5 | 5 | 4 (4): e7 e9 e15 e16 | 5 / 10 | 9 | 0 | 100~118 |
| R2 | 16 / 16 | 16 (15) | **수락**, 위반 없음 | 4 | 4 | 3 (2): e2 e12 e14 | 4 / 9 | 7 | 0 | 134~203 |
| R3 | 19 / 24 | 23 (23) | **수락**, 위반 없음 | 5 | 5 | 1 (1): e_revinv_requires_grade | 6 / 17 | 6 | 0 | 128~215 |
| 합 | 107 / 114 | 113 | 6건 모두 수락 | **26** | 26 | **24** | 26 / 64 | 50 | 0 | 74~215 |

읽은 것:
- **6건 모두 v.8에서도 L1을 통과한다.** 위반 코드는 하나도 없다. 다리 요약이 없거나 짧아서 실패한 실행도 **없다.** v.7 프로토콜은 다리 요약을 요구하지 않았지만, 합성 에이전트 6개가 모든 다리에 요약을 적었다(정규화 후 74~215자, 하한 40 위). MUST-Q7 틀 문장 비율은 6건 모두 0이다.
- **창발 엣지가 113개에서 24개로 줄었다.** 엣지 중 창발 비율이 99%에서 21%가 됐다. 빠진 것은 질의 노드에 닿는 엣지와 자기 앵커 엣지다. §9 (v.8) 행의 예측("창발 엣지 1~7개, 다리 4~5개, 6건 모두 MUST-Q3 통과")과 같다.
- **v.8 다리 26개 = 오너가 HUMAN-001에서 평가한 다리 26개.** 실행마다 다리 ID 집합이 평가 데이터(`$LLM/rating_data.json`)의 다리 ID와 정확히 같다. v.8의 평가 단위는 오너가 실제로 판단한 단위를 그대로 담는다.
- **R3은 창발 엣지가 1개뿐이다.** 다리 5개가 대부분 질의 엣지와 자기 앵커 엣지로만 이어져 있다. 평가 단위 6개 중 5개가 다리다. Q3은 호스트 다리로 충족된다.
- **`bridges_with_constraints`는 모두 0이다.** v.7에는 `constraints` 필드가 없었으므로 예상한 값이다. 거부 사유가 아니라서 결과에는 영향이 없다. 다음 합성(v.8 프로토콜)에서 채운 수가 처음 나온다.

출력: `$I/regress6.json`(실행별 위반·집합·요약 길이), `$I/xcheck.py`(독립 대조).

## 8. 해석 — 오너 확인이 필요한 것

1. **보이는 델타브레인에서 모르는 `target_id` → `NOT_RATEABLE` (통합 담당 결정).** §9 (v.8) "아니면 `NOT_RATEABLE`"을 문장 그대로 따랐다. Builder는 처음에 `NOT_FOUND`를 돌려줬고, 테스트 작성자는 이것을 유일한 해석 차이로 보고했다. 참여자는 모든 노드·엣지 ID를 보므로(NEVER-02) 어느 쪽도 존재를 새지 않는다. `NOT_FOUND`(델타브레인이 없거나 비참여자)는 그대로다. 오너가 다르게 정하면 `service.py` 한 줄과 테스트 4곳을 바꾸면 된다.
2. **`bad-templated.json`이 v.8에서 수락된다 (고정 fixture 충돌).** §6.4는 여전히 `TEMPLATED_RATIONALE`을 기대한다. 하지만 v.8 MUST-Q7은 평가 단위만 센다. 이 파일의 틀 문장은 e5·e6·e7(자기 앵커, 평가 단위 아님)과 e10에만 있어 6단위 중 중복 0개다.
   - 테스트 작성자가 새 golden `bad-templated-02.json`을 더했다. good-01과 같고, 창발 엣지 e4·e9·e10에 같은 틀 문장이 있어 3/6이다. 작업 트리 검증기는 이 파일에 `TEMPLATED_RATIONALE` 하나만 낸다.
   - 통합 담당이 `fixtures/deltabrains/*.json` 16개를 §6.4 컨텍스트(`fixture_canal_context`)로 직접 다시 돌렸다. `good-01`은 수락, `bad-*`는 모두 목표 코드가 나온다. 예외는 `bad-templated.json`(수락)과 `bad-host-untouched.json`(아래 3)뿐이다.
   - §6.4 표에 이 파일 행을 넣을지, `bad-templated.json` 행을 어떻게 할지 오너가 정해야 한다.
3. **`bad-host-untouched.json`에 위반이 하나 더 나온다.** 목표 코드 `HOST_NOT_TOUCHED`는 그대로 나온다. 그런데 유일한 다리 n-bc의 요약이 정규화 후 27자라 `RATIONALE_MISSING`(node_id n-bc)도 나온다. 테스트는 이 코드를 허용으로 두었다. §6.4 표에 함께 적을지 정해야 한다.
4. **품질의 분모 = 평가된 단위.** HUMAN-01 "세 축이 모두 1인 평가 단위 비율"을 평가된 단위 중 비율로 읽었다(테스트 작성자·Builder 공통). 전체 단위로 나누면 평가하지 않은 단위가 0점처럼 계산된다. 평가자가 여럿이면 모든 평가가 1/1/1인 단위만 "좋음"이다.
5. **응답 모양 중 계약에 없는 것.**
   - `rating_summary`의 키(`rating_unit_count`, `bridge_node_count`, `emergent_edge_count`, `rated_unit_count`, `quality`)와 `untrusted_data.ratings.units[]`(target_id, kind, raters, …)는 Builder가 정했다. 예전 `rated_emergent_edge_count`와 `ratings.edges`는 없어졌다. oracle 테스트는 키 이름을 고정하지 않았다.
   - TASK §5는 `untrusted_data.stats`라고 적었지만, 구현은 v.3부터 `untrusted_data.deltabrain.stats`를 쓴다.
6. **v.8 이전 레코드도 v.8 규칙으로 다시 계산해 보여준다.** 저장된 `stats_json`에 `bridge_node_ids`가 없으면(`model_fields_set`으로 판별) 보는 사람 통계를 v.8로 다시 계산한다. 레코드 자체는 그대로 둔다.
   - 결과: 오너의 측정용 DB에서도 다리를 평가할 수 있다.
   - 대신 HUMAN-001에서 v.7 창발 엣지에 기록한 평가 106건 중 질의 엣지·자기 앵커 엣지에 붙은 것은 `edge_ratings` 테이블에는 남지만, `ratings.units`·`mine`·`quality`에서는 빠진다. 다리 평가는 그 DB에 아직 없다(오너 평가가 엣지로 옮겨 기록됐기 때문). 그래서 그 DB의 `quality`는 HUMAN-001 §2의 다리 기준 값과 다르다.
7. **다리 요약의 틀 비교에는 라벨 자리표시자를 쓰지 않는다.** MUST-Q7은 "rationale 안의 양 끝 노드 라벨"만 자리표시자로 바꾼다고 적었으므로, 다리 요약은 정규화한 문장 그대로 비교한다. 다리 요약에도 같은 처리를 하려면 Oracle 변경이 먼저다.
8. **`docs/DECISIONS.md` 50행.** `deltabrain_rate`를 아직 "창발 엣지에 L2 라벨"로 적고 있다. 고정 문서라 고치지 않았다.

## 9. 남은 위험

| 위험 | 내용 | 정도 |
|---|---|---|
| golden 표와 동작이 다름 | §6.4의 `bad-templated.json` → `TEMPLATED_RATIONALE`은 v.8 구현과 맞지 않는다(§8.2). strict xfail로 표시만 했다. 새 golden `bad-templated-02.json`은 §6.4에 없고 오너 검토 전이다 | 중간 (오너 결정 대기) |
| `NOT_RATEABLE` 해석 | §8.1. Oracle 문장을 따랐지만 테스트 작성자가 오너 확인을 요청한 항목이다 | 낮음 |
| 측정 DB의 품질 값 | §8.6. v.7 시절 엣지 평가 중 일부가 집계에서 빠져, 같은 DB에서 보는 `quality`가 HUMAN-001 다리 기준 값과 다르다. 비교하려면 다리 26개를 `target_id`로 다시 기록해야 한다 | 중간 (측정용 데이터) |
| 노드·엣지 ID 이름공간 | 노드 ID와 엣지 ID는 이름공간이 달라서, 한 ID가 다리이면서 창발 엣지일 수 있다. 이때 평가 단위 하나로 세고 kind는 `bridge_node`다. 평가는 ID로 저장되므로 두 단위를 따로 평가할 수 없다. 검증기는 노드·엣지 ID 충돌을 막지 않는다 | 낮음 (합성기가 같은 ID를 쓸 때만) |
| 같은 정의의 두 구현 | 다리·창발·자기 앵커 판정이 `validator.py`와 `store.py`(`_stats_over_keys`, 가린 신원 기준)에 따로 있다. `test_viewer_stats_rules_match_the_validator_when_nothing_is_masked`가 둘이 같은지 지킨다. 한쪽만 고치면 이 테스트가 잡는다 | 낮음 |
| `constraints` 품질 | 채운 수만 센다. 내용은 검사하지 않는다(오너 결정: 거부 사유 아님). 짧거나 형식적인 `constraints`도 1로 센다 | 낮음 (L2·L3 몫) |
| 자기 앵커는 유효 출처만으로 판정 | 무효 출처가 섞인 제출은 어차피 거부되므로 차이는 거부된 제출의 통계에만 나타난다 | 낮음 |
| 혼자 라벨 | HUMAN-01은 여전히 오너 혼자 라벨한다(§7 공통모드 위험 "높음"). v.8은 단위를 바꿨을 뿐이다 | 기존 그대로 |

## 10. 동시 편집 확인

통합 도중 `src/opencanal/*.py`, `tests/oracle/*.py`, `tests/unit/*.py`, `fixtures/deltabrains/*.json`의 해시를 떠 두었다(`$I/hashes_mid.txt`). 이 문서를 쓴 뒤 다시 비교했다. 달라진 파일은 없었다. 통합 담당이 고친 `service.py`, `test_unit_service.py`, `test_unit_integration.py`는 해시를 뜨기 전에 고쳤다. `git worktree list`에는 본 작업 트리만 있고, `git stash list`는 비어 있다.

## 11. 적대 확인 (2026-10-07, 통합 담당)

적대 검토에서 v.8 src 결함 2건이 나왔다. 반박 담당이 두 건 모두 따로 재현해 반박하지 못했다(N11-V8-RATE-1 높음, N11-V8-RATE-2 중간). 근거 Oracle 줄은 세 가지다.
- NEVER-11 (v.4 문장): "통계(창발 엣지 목록, 관여 주인 수), 평가 응답, 오류 코드로도 비공개 기여자가 누구인지(보이는 다른 기여자와 같은 사람인지) 계산할 수 없다. 그 참여자에게 보이는 통계는 그에게 보이는 신원 기준으로 계산한다."
- HUMAN-01 (v.8): 평가 단위는 다리 노드 ∪ 창발 엣지다.
- §7: HUMAN-01은 오너 혼자 라벨한다.

### 11.1 결함

두 세계는 비공개가 된 C의 주인만 다르다. 'distinct'에서는 user_c, 'same'에서는 user_b(공개 B의 주인)다. 보는 사람 user_a·user_e는 두 세계 모두 C를 "비공개 기여자"로 본다. 고치기 전에는 이들의 `deltabrain_get`이 두 세계에서 달랐다. 통계, `NOT_RATEABLE` 코드, 보는 사람 자신의 평가 응답은 두 세계에서 같았다. 다른 것은 여러 평가자의 행을 합친 집계뿐이었다.

| ID | 경로 | 고치기 전 차이 (distinct vs same) |
|---|---|---|
| N11-V8-RATE-1 | `_ratings_summary`가 모든 평가자의 행을 합산하고, 걸러 내는 기준은 보는 사람의 평가 단위뿐이었다. 각 행은 평가한 사람 자신의 뷰로 받아들여진 것이다. B와 C의 주인이 같은 user_b는 n3·e9·e12에 `NOT_RATEABLE`을 받으므로, 같은 주인 세계에서만 이 세 단위에 평가가 비어 있다 | A(user_b만 비공개 뒤 평가): `rating_summary.rated_unit_count` 9 vs 6. B(비공개 **전** 평가): 9 vs 6. D(a·e·b 평가): n3·e9·e12의 raters 3 vs 2. F(user_a 1/1/1, user_b 0/0/0): `quality` 0.0 vs 0.333 |
| N11-V8-RATE-2 | 단위별 평가자 수는 실제 참여자 수의 하한이다. 보이는 신원보다 평가자가 많으면 가린 주인이 새 사람이라는 것이 확정된다 | E(모든 참여자가 n1만 평가): n1 raters·all_three 4 vs 3 |
| (통합 담당 추가) G | 인용되지 않은 멤버가 비공개인 경우다. Q-01 커널의 멤버 A2는 good-01이 인용하지 않는다. A2의 주인을 user_e와 user_b로 나눈 두 세계에서 A2를 비공개로 하면, 델타브레인 뷰에는 가린 기여자가 **없다**. `canal_get`에서만 withheld로 보인다 | 모든 참여자가 n1 평가: raters 4 vs 3 (user_a, user_c 둘 다). 따라서 "델타브레인 뷰에 비공개 기여자가 있을 때"만 보고 집계를 끄면 이 경우는 막지 못한다 |

v.7 HEAD의 `_ratings_summary`도 창발 엣지에 대해 같은 방식으로 합산했다. 그러니 v.8에서 새로 생긴 결함은 아니다. 다만 v.8에서는 다리 노드(n3)도 가림 여부에 따라 갈리므로 새는 폭이 넓어졌다.

### 11.2 고친 것 (`src/opencanal/service.py`만)

- **`Service._withholds_anything(user, view)`를 새로 만들었다.** 보는 사람에게 가려진 것이 하나라도 있으면 참이다. 가려진 것은 두 가지다.
  - 델타브레인 뷰의 `contributors` 중 `owner_id`가 null인 항목("비공개 기여자").
  - `canal_get`에서 withheld로 보이는 호스트나 멤버. 인용 여부와 관계없고, `canal_get`과 같은 `_visible_in_canal` 판정을 쓴다.
- **`_ratings_summary(..., own_only=)`를 바꿨다.** 참이면 보는 사람 **자신의** 평가 행만 센다. 대상은 `rating_summary`(최상위 숫자 5개)와 `untrusted_data.ratings`(units, mine)다. 어느 쪽을 셌는지는 `untrusted_data.ratings.scope`(`"own"` 또는 `"all"`)로 알린다.
- **바꾸지 않은 것**: `deltabrain_rate`의 판정과 `NOT_RATEABLE`, 통계, `rating_summary`의 키, 저장된 평가 행.

판단 근거.
- **스위치 자체가 새 경로가 아니다.** 스위치의 입력은 "가려진 것이 있는가"다. 이것은 그 참여자에게 이미 보이는 사실이다(`canal_get`의 withheld 항목, 비공개 기여자). 두 세계에서 같다. G 재현에서 `canal_get`이 두 세계에서 같은 것도 확인했다.
- **항상 자기 평가만 보이게 하지는 않았다.** oracle `test_v8_rate_is_an_upsert_per_rater_and_target`은 아무것도 가려지지 않은 커널에서, 평가하지 않은 user_b의 `deltabrain_get`에 다른 사람이 평가한 n1이 나와야 한다고 요구한다. 가려진 신원이 없으면 재식별할 대상도 없다. 이때는 지금처럼 모두의 평가를 센다.
- **가린 평가자만 빼는 방법은 쓰지 않았다.** RATE-2만 막고 RATE-1은 막지 못한다. RATE-1에서 문제의 평가자 user_b는 B의 주인으로 평문으로 보이기 때문이다(적대 검토의 지적과 같다).
- **평가 시점의 판정만 바꾸는 방법도 쓰지 않았다.** 재현 B처럼 공개 시절에 저장된 행이 이미 진짜 구조를 담고 있다. 그래서 읽는 쪽에서 막았다.
- **측정에는 영향이 없다.** HUMAN-01은 v0에서 오너 혼자 라벨한다(§7). 오너 자신의 평가와 품질은 그대로 보인다.

### 11.3 재현 전후

모든 재현은 저장소 밖에서 실행했다. DB는 메모리 또는 scratch에 두었고, 키는 scratch에 두었다. 저장소 파일은 쓰지 않았다.

| 재현 (스크립트) | 고치기 전 | 고친 뒤 |
|---|---|---|
| A~E (`$V/never11-rate/repro_rating_channel.py`) | 다섯 시나리오 모두 두 보는 사람 `identical across worlds: False` | 모두 `True`, `"leak": false` |
| F (같은 스크립트, `ONLY_F=1`) | `quality` 0.0 vs 0.333 | `True` |
| 반박자 최소 재현 (`$V/refute-n11-rate/mine/check.py`) | `rated_unit_count` 9 vs 6 | 두 세계 모두 0, `quality` null (user_a는 평가하지 않았다) |
| 반박자 E 재현 (`$V/refute-n11-rate-2/repro_e.py`) | n1 (raters, all_three) (4,4) vs (3,3) | 두 세계 모두 (1,1) |
| G (`$V/integ-rate/repro_uncited_member.py`, 신규) | raters 4 vs 3 | 두 세계 모두 1, `LEAK: False` |

### 11.4 테스트

- **`tests/unit/test_unit_integration.py`** (실제 Store와 Service)
  - `_same_owner_canal`에 인자 두 개를 더했다. `cite_b2`가 False면 B2를 인용하지 않는 커널 멤버로만 둔다. `before_hide`는 비공개 전에 실행할 훅이다. 기존 테스트의 반환 키는 그대로다(`ids` 하나 추가).
  - 신규 `test_other_participants_ratings_do_not_reidentify_a_masked_contributor`를 5개 매개변수로 더했다: `masked_owner_after`, `masked_owner_before`, `everyone_one_bridge`, `quality_split`, `uncited_everyone_one_bridge`.
  - 매 경우 저장된 평가 행이 두 세계에서 **다르다**는 것을 먼저 확인한다(빈 비교 방지). 그다음 user_a·user_c의 `deltabrain_get`이 두 세계에서 같은지, `scope`가 `"own"`인지 단언한다. B2 주인은 `"all"`이어야 한다.
- **`tests/unit/test_unit_service.py`** (FakeStore)
  - `view_contributors`를 더했다. 기본값은 비어 있어 기존 테스트에는 영향이 없다.
  - 신규 `test_deltabrain_get_counts_only_own_ratings_once_anything_is_withheld`는 세 가지를 고정한다. 가려진 것이 없으면 모두의 평가(raters 2), B가 비공개면 user_a·user_c는 자기 것만, B 주인은 모두의 것을 본다. 뷰의 비공개 기여자만으로도 스위치가 켜진다.
- **빨강**: 고치기 전 코드에서 확인했다.
  - 저장소의 새 테스트 6개가 모두 실패했다. `scope` 키가 없어서다.
  - 이것만으로는 증거가 약해서, `scope` 단언을 뺀 사본(`$V/integ-rate/red/test_red_integration.py`)도 돌렸다. 통합 테스트 5개가 모두 **두 세계 비교 단언**에서 실패했다(raters 3 vs 4 등).
- **초록**: 전체 **1880 passed, 1 xfailed**다(`umask 022`). oracle은 918 + xfail 1로 §5와 같고, unit은 962로 §5보다 6개 늘었다. `PYTHONHASHSEED` 0, 1, 12345에서도 같았다.
- **실제 델타브레인 6건**: `$I/regress6.py`의 출력(`$I/regress6_after_rate_fix.json`)이 §7의 `$I/regress6.json`과 바이트 단위로 같다. `$I/xcheck.py`도 6건 모두 일치한다. `validator.py`는 바뀌지 않았다.
- **고정 파일**: `git diff HEAD --stat -- docs config fixtures src/opencanal/models.py src/opencanal/textnorm.py src/opencanal/config.py pyproject.toml tasks`의 출력은 비어 있다.
- **동시 편집**: §10의 `$I/hashes_now.txt`와 비교했다(`$I/hashes_after_rate_fix.txt`). 바뀐 파일은 `service.py`, `test_unit_integration.py`, `test_unit_service.py` 셋뿐이다. 그래서 §10의 해시 스냅샷은 이 세 파일에 대해 낡았다.

### 11.5 Oracle 테스트 빈틈 (테스트 작성자·계획 담당에게)

`test_oracle_v8_service.py::_world`와 `test_oracle_v4_exposure.py::_never11_world`의 두 세계 비교에서는 평가자가 보는 사람(user_a, user_e)뿐이다. 가린 주인(same 세계의 user_b, distinct 세계의 user_c)이 평가하는 경우가 없어서, 이번 결함은 919개 oracle 테스트가 모두 초록인 상태에서 남아 있었다. 다음을 두 세계에서 똑같이 실행한 뒤, user_a·user_e의 `deltabrain_get`(`rating_summary`, `untrusted_data.ratings`)이 같은지 단언하는 테스트가 필요하다.
1. C를 비공개로 한 뒤 user_b가 모든 ID를 평가한다.
2. 1과 같은 평가를 C가 공개일 때 한다.
3. 모든 참여자가 n1만 평가한다(distinct 세계는 참여자가 하나 더 많다).
4. user_a는 1/1/1, user_b는 0/0/0으로 평가한다.
5. 인용되지 않은 멤버(A2)가 비공개인 세계 쌍에서 3을 한다.

어떤 고침이 맞는지(자기 평가만, 집계 생략 등)는 Oracle이 정하지 않는다. 그러니 테스트는 "두 세계에서 같다"만 단언해야 한다. `scope` 키 이름도 고정하지 않는 것이 맞다.

### 11.6 오너 확인이 필요한 것

1. **가려진 것이 있으면 자기 평가만 보인다 (Builder 결정).** §7(오너 혼자 라벨)과 맞는다.
   - R1에서 라벨러를 늘리면, 가린 기여자가 있는 커널에서는 도구로 다른 평가자의 집계를 볼 수 없다.
   - 여러 평가자의 품질은 서버 운영자가 도구 밖에서 `edge_ratings` 테이블로 집계해야 한다. 이 방식을 받아들일지 정해야 한다.
2. **`untrusted_data.ratings.scope`는 계약(TASK §5)에 없다.** §8.5의 `units[]`처럼 Builder가 정한 모양이다.
3. **보는 사람 자신이 비공개 전에 남긴 평가.** C가 공개일 때는 C의 주인이 평문으로 보였다. 그래서 그때 남긴 자기 평가 행은 두 세계에서 다를 수 있다(same 세계에서는 그때 e9가 `NOT_RATEABLE`). 그 참여자가 이미 알던 정보라 NEVER-11 범위 밖으로 보았다. 막지 않았다.
4. **`deltabrain_get` 한 번에 조회가 늘었다.** `get_canal_for_viewer`와 `canal_context`가 하나씩 더해진다. 규모가 작아 운영 영향은 없다고 본다.

## 부록 — v.9 보충 (플래너, 통합 뒤)

v.8 적대 검토에서 Oracle 정의의 빈틈 2건이 확인됐다(반박 에이전트가 "구현 결함 아님, Oracle 빈틈"으로 판정). Oracle → 테스트(빨강) → 구현 순서로 고쳤다.

| 빈틈 | Oracle v.9 | 테스트 (`tests/oracle/test_oracle_v9_gaps.py`) | 구현 |
|---|---|---|---|
| V8-L1-RATE-COLLIDE-1: 다리 노드와 창발 엣지가 같은 ID면 평가 단위가 하나로 합쳐짐 | MUST-Q0: 노드 ID와 엣지 ID가 겹치지 않는다 | `test_must_q0_v9_node_and_edge_ids_must_not_overlap` (빨강 → 초록) | `validator._check_graph_schema` |
| V8-L1-Q7-SUMMARY-TEMPLATE-1: 다리 요약을 자기 라벨만 바꾼 틀 문장으로 채우면 통과 | MUST-Q7: 다리 요약은 자기 라벨을 자리표시자로 바꿔 비교 | `test_must_q7_v9_bridge_summaries_differing_only_by_own_label_are_templated` (빨강 → 초록) | `validator._explanations` |

- 같이 명시한 것: 품질 분모는 "평가된" 단위(HUMAN-01), 보이는 델타브레인의 모르는 `target_id`는 `NOT_RATEABLE`(§9), §6.4의 `bad-templated.json`(v.8부터 수락)과 `bad-templated-02.json`(v.8 추가), `bad-host-untouched.json`의 `RATIONALE_MISSING` 동반.
- 단위 테스트 `test_bridge_summaries_are_compared_with_their_own_label_substituted`는 v.9 규칙에 맞춰 바꿨다(예전 이름은 "라벨 치환 없음"을 고정했다).
- **실제 델타브레인 영향:** v.9 MUST-Q0 때문에 F1·F2가 `SCHEMA_INVALID`로 거부된다. 합성 에이전트가 원본 노드 ID(`e9`, `e10`)를 그대로 앵커 노드 ID로 써서 자기 엣지 ID와 겹쳤다. 거부가 맞다(평가 대상이 모호해진다). 합성기가 미리 피하도록 프로토콜 규칙 첫 줄에 "노드·엣지 ID는 서로 겹치지 않게, 원본 노드 ID를 그대로 쓰지 말 것"을 넣었다. 나머지 4건(F3, R1~R3)은 그대로 통과한다.
- 전체 결과(umask 022): 1883 passed, 1 xfailed.
