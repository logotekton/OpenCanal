# CHANGE-006 — Oracle v.7 통합 기록 (거리 = 호스트 낱말 겹침 비율, 낱말 채우기로 거리 조작 불가)

> NDSH 부록 B-7 양식. 통합 담당(Integrator)이 2026-10-06~07에 남긴 기록이다. 사실만 적는다.
> 기준 문서는 `docs/oracle/ORACLE_MANIFEST.md` v2026-10-06.7이다. 그중 MUST-M5, MUST-M2, §9 "(v.7)" 행, §10 "관련도 낱말 채우기" 행을 따른다. 기준 커밋은 `1641879`이며, 이번 작업은 커밋하지 않았다.
> 작업 파일 위치: `$V`는 이 세션 scratchpad의 `v7/`, `$I`는 `$V/integrator/`다. 둘 다 저장소 밖에 있다. 기준선 worktree는 `$V/integ-base`에 만들었다가 지웠다(`git worktree list`는 본 작업 트리 하나만 보인다).

## 1. v.7을 왜 바꿨나 — M5-PAD-1

v.6의 MUST-M5는 노드 라벨·태그·요약의 낱말 빈도 벡터 코사인으로 거리를 쟀다. 코사인은 후보의 벡터 길이로 나누므로, 후보가 호스트에 없는 낱말을 덧붙일수록 코사인이 작아지고 거리가 커진다. 후보가 스스로 "먼 분야"가 되어 MUST-M2 가산점(`distance_bonus` × 거리)과 다양성 보장의 "먼 후보" 자리를 살 수 있었다. 적대 검토 M5-PAD-1에서 확인됐다(§9 (v.7) 행: "관계없는 낱말 하나를 반복해 채우면 후보가 스스로 거리를 키워 가산점과 먼 후보 자리를 차지할 수 있었다").

통합 담당이 v.6 코드(`git archive 1641879 src`)로 같은 공격을 다시 돌려 확인한 값(§8):
- 호스트 A와 같은 분야인 A2(거리 0)가 "쿼쿼" 노드(라벨 1 + 같은 태그 20)를 1개 붙이면 거리 0.2034, 2개면 0.5379(먼 후보), 5개면 0.8055가 됐다.
- Q-01에서 max_members 1이면 원래 C가 뽑힌다. 그런데 A2에 5개를 붙이면 A2(점수 0.8016)가 뽑혔다.
- 같은 분야 복제본 3개(다른 주인)에 "쿼쿼" 노드를 3개씩 붙이면 Free 3자리를 모두 차지했다(거리 0.9411, 점수 0.8823). B·C는 잘렸다.

v.7 정의(MUST-M5): **유사도 = |H ∩ C| ÷ |H|**. H와 C는 노드 **라벨과 태그**에서 `textnorm.tokenize`(조사 제거, 불용어 제거)로 뽑은 서로 다른 낱말의 **집합**이다. **거리 = 1 − min(1, 유사도 ÷ `distance_saturation`)**이고, H가 비면 1이다. 계산은 유리수로 정확히 한다. 분모가 호스트 낱말 수이므로, 후보가 호스트에 없는 낱말을 덧붙여도 분자와 분모 모두 변하지 않는다. 요약은 "된다·한다" 같은 서술 낱말이 섞여 같은 분야와 먼 분야의 구분을 흐렸기 때문에 뺐다(§9 (v.7)).

| # | 기준 | Oracle 줄 | 구현 반영 | 고정한 테스트 |
|---|---|---|---|---|
| 1 | 거리 = 호스트 낱말 중 후보도 가진 비율 | MUST-M5 (v.7 정의 변경). §9 (v.7) "fixture: 라벨·태그만 쓰면 A2 0.278, B·C 0.056, D·X 0" | `matching._content_words`가 라벨·태그 낱말 집합을 만든다(`host_terms`와 같은 토큰화). `_distance_between`은 `Fraction`으로 `1 − min(1, Fraction(공통, |H|) ÷ Fraction(str(saturation)))`를 계산한다. H가 비거나 공통 낱말이 없으면 1이다. 코사인, 빈도 벡터, `isqrt`, float 대체 경로는 지웠다. `_Scored.distance`는 늘 `Fraction`이다. 호스트 집합은 `match_with_ranking` 한 번에 한 번만 만든다 (Builder) | `test_oracle_v7_matching.py` 37개, `test_unit_matching_distance.py` 39개 |
| 2 | 채운 낱말은 거리를 바꾸지 않는다 | MUST-M5 "후보가 호스트와 겹치지 않는 낱말을 아무리 덧붙여도 거리는 변하지 않는다". 금지 결과 "낱말 채우기·반복으로 거리를 키울 수 있음" | 위 정의에서 따라 나온다. 따로 분기는 없다 | `test_must_m5_v7_padding_with_foreign_words_never_changes_the_distance[8가지]`, `test_must_m2_v7_padded_near_host_clones_*` 2개 |
| 3 | 요약·노드 유형·엣지·제목·분야는 쓰지 않는다 | MUST-M5 "요약, 노드 유형, 엣지, 제목, 신고한 분야(`domains`)는 쓰지 않는다" | `_label_tag_texts`가 라벨과 태그만 넘긴다 | `test_must_m5_v7_host_words_outside_labels_and_tags_*`, `…_host_summaries_types_edges_title_and_domains_do_not_count[bare,stuffed]`, v6 파일의 `test_must_m5_other_fields_do_not_count[summary 포함 5가지]` |
| 4 | 정확한 계산과 동점 규칙 | MUST-M5 "계산은 정확해야 하고(유리수)". MUST-M2 "같으면 관련도, 그다음 subbrain_id 오름차순" | 거리·관련도·점수가 모두 `Fraction`이다. Q-01에서 B·C는 점수 19/30, 관련도 0.40으로 정확히 같다. 그래서 subbrain_id가 순서를 정한다 | `test_must_m5_v7_rationally_equal_coverages_give_exactly_equal_distances[5그룹]`, `test_must_m5_v7_same_number_of_shared_words_is_a_full_tie_broken_by_subbrain_id` |

표의 구현 세부는 빌더 보고에서 옮겼다. 통합 담당이 직접 확인한 것은 다섯 가지다.
- §4 빨강 기준선 54건(+ sid에 따라 흔들리는 1건)이 지금은 모두 초록이다. `matching.py` 하나만 바꿔도 모두 초록이 된다(§4 (c1)).
- §7 스모크의 거리·점수가 §9 (v.7) 숫자, 그리고 `matching.py`와 `_v7.py`를 쓰지 않는 독립 계산(§7.3)과 일치한다.
- §8 채우기 공격 재실행에서 v.6 코드는 거리와 선택이 바뀌었다. 작업 트리 코드는 하나도 바뀌지 않았다.
- 고정 파일은 바뀌지 않았다(§2).
- 통합 중 다른 에이전트가 파일을 바꾸지 않았다(§11).

## 2. 변경 요약

병렬 단계에서는 두 명이 작업했다.
- **테스트 작성자(Oracle 쪽)**: `tests/oracle/_v7.py`(정확한 `Fraction` 기준 구현과 손으로 만든 문서들)와 `test_oracle_v7_matching.py`(37개)를 새로 만들었다. `_v6.py`는 지우고, 그것을 import하던 네 곳을 `_v7`로 바꿨다. 기존 oracle 파일 5개를 고쳤다(§6).
- **Builder**: `src/opencanal/matching.py`와 단위 테스트 4개 파일(`test_unit_matching.py`, `test_unit_matching_distance.py`, `test_unit_matching_exact_ties_v6.py`, `test_unit_service_v6.py`)을 맡았다.

통합을 시작할 때 작업 트리는 이미 **1656 passed**였다. Builder 보고의 "1577 passed, 1 collection error"는 테스트 작성자가 `_v6.py`를 지운 뒤 v6 테스트 파일을 아직 고치기 전 시점의 값이다. 통합 단계에서는 실패를 고칠 것이 없었다. 남은 v.6 문구만 고쳤다.

### 2.1 통합 단계에서 직접 바꾼 것

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/opencanal/service.py` `canal_get` 주석 1곳 | "the content distance from the host's labels, tags and summaries"를 "the share of the host's label/tag words the member also has (MUST-M5 v.7)"로 바꿨다 | v.6 문구가 남아 있었다. 주석만 바꿨고 동작은 그대로다 |
| `README.md` match-explain 설명 | "노드 라벨·태그·요약 낱말로 계산한 내용 거리"를 v.7 정의로 바꿨다. 호스트 라벨·태그 낱말 중 후보도 가진 비율이고, 덧붙인 낱말은 거리를 바꾸지 않으며, 요약·노드 유형·엣지·제목·분야는 쓰지 않는다 | 사용자가 보는 설명을 실제 동작에 맞췄다 |
| `evidence/CHANGE-006.md` (신규) | 이 문서 | |

`service.py`와 `cli.py`에서 거리를 직접 계산하는 곳은 없다. `content_distance`, `_distance_between`, `_content_words`는 `matching.py` 안에서만 부른다(grep으로 확인). v.7 거리는 호스트 기준이라 대칭이 아니지만, 인자 순서를 뒤집어 부르는 호출 지점은 없다. 도구 설명(`match_explain`의 "내용 거리, 점수")은 v.7에서도 맞으므로 그대로 두었다.

고정 파일(`docs/`, `config/`, `fixtures/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. `git diff HEAD --stat -- docs config fixtures src/opencanal/models.py src/opencanal/textnorm.py src/opencanal/config.py pyproject.toml`의 출력은 비어 있다. **고정 파일에 남은 v.6 문구 하나를 보고한다.** `src/opencanal/config.py` 28행 주석은 "`distance = 1 - min(1, cosine / distance_saturation)`"이다(Oracle ID MUST-M5 v.7). 동작에는 영향이 없다. TASK 갱신으로 고칠 일이다. 스키마 변경은 없다.

## 3. 실행 명령

```bash
# 자동 검사 (저장소 루트)
umask 022; .venv/bin/python -m pytest -q -p no:cacheprovider

# 빨강 기준선 (저장소 밖 worktree)
git worktree add --detach $V/integ-base 1641879
cd $V/integ-base && export PYTHONPATH=$V/integ-base/src && umask 022
<repo>/.venv/bin/python -m pytest -q -p no:cacheprovider                         # (a) 커밋된 테스트 그대로
git rm -q tests/oracle/_v6.py
cp <repo>/tests/oracle/{_v7.py,test_oracle_v7_matching.py,test_oracle_matching.py,test_oracle_v4_matching.py,\
test_oracle_tiers.py,test_oracle_v5_matching.py,test_oracle_v6_matching.py} tests/oracle/
<repo>/.venv/bin/python -m pytest -q -p no:cacheprovider tests/oracle -rf         # (b) 새 oracle 파일 (4번)
cp <repo>/src/opencanal/matching.py src/opencanal/; pytest tests/oracle; git checkout -- src   # (c1)
cp <repo>/tests/unit/{test_unit_matching,test_unit_matching_distance,test_unit_matching_exact_ties_v6,\
test_unit_service_v6}.py tests/unit/; pytest <그 4개>                              # (d) 빌더 단위 테스트
git worktree remove --force $V/integ-base && git worktree prune

# 스모크: zsh $I/smoke.sh $I r1 ; zsh $I/smoke.sh $I r2   (출력 $I/smoke_out_r{1,2}.txt, 토큰은 가렸다)
# 독립 계산: .venv/bin/python $I/indep_check.py
# 채우기 공격 재실행 (v.6 = git archive 1641879 src, v.7 = 작업 트리):
cd $I/padding
OC_SRC=<v6src 또는 repo>/src TMPDIR=$I/padding/tmp python exp1_padding.py
OC_SRC=… TMPDIR_BASE=$I/padding/tmp OPENCANAL_CONFIG_DIR=<repo>/config python e2e_padding.py
```

참고 사항 둘.
- **기준선 import 경로.** worktree 안에서 `import opencanal`이 worktree의 `src`를 가리키는 것을 확인했다(`opencanal.__file__` 출력).
- **(b)의 `_v6.py` 삭제.** 작업 트리에서 `_v6.py`는 지워졌고 이를 import하는 곳도 없다. 그래서 기준선에서도 지운 상태로 돌렸다. `git stash`는 쓰지 않았다. 실행 전후 `git stash list`는 비어 있었다.

## 4. 빨강 기준선

| 실행 | 결과 | 해석 |
|---|---|---|
| (a) `1641879` 그대로 (커밋된 테스트) | **1611 passed** | 작업 지시와 같다. v.7은 매니페스트에만 있고 코드와 테스트에는 아직 없었다 |
| (b) (a)에 새·수정 oracle 파일 7개, `_v6.py` 삭제 (tests/oracle 772개) | **55 failed, 717 passed** (4번 실행: 55 / 54 / 55 / 55) | 늘 실패하는 54건과, 무작위 subbrain_id에 따라 실패하는 1건. 파일별: v7_matching 26, v6_matching 19(+1), v5_matching 7, matching 1, v4_matching 1. 늘 실패하는 54건은 테스트 작성자가 보고한 목록(`$V/oracle/baseline_failures.txt`)과 한 줄도 다르지 않다 |
| (c1) (b)에 작업 트리 `matching.py`만 넣음 | **772 passed** | 빨강 55건이 모두 `matching.py` 하나로 초록이 된다 |
| (d) 기준선 src에 빌더의 단위 테스트 4개 파일 | 64 failed, 90 passed | 파일별: `test_unit_matching_distance.py` 34, `test_unit_matching_exact_ties_v6.py` 15, `test_unit_matching.py` 14, `test_unit_service_v6.py` 1. 단위 테스트도 v.6 코드를 잡는다 |

**흔들리는 1건.** `test_oracle_v6_matching.py::test_must_m2_v6_canal_open_q01_expert_host_orders_members_by_score`가 그것이다. 이 테스트는 멤버 순서만 본다. v.6에서는 C(0.6439)가 B(0.6260)보다 위이고, v.7에서는 B·C가 비겨 subbrain_id 오름차순이다. 그래서 서버가 무작위로 만든 sid(B)가 sid(C)보다 클 때는 v.6에서도 통과한다. 기준선에서 따로 12번 돌렸더니 7번 통과, 5번 실패했다. 이 테스트 자체는 v.7에 맞는 테스트다(테스트 작성자 보고와 같다). 같은 사실을 늘 잡는 테스트가 따로 있다. `test_oracle_v7_matching.py::test_must_m2_v7_canal_open_q01_expert_host_b_and_c_tie_above_a2`가 거리·관련도·점수가 정확히 같은지 확인하고, 기준선에서 4번 모두 빨강이었다.

**실패 내용** (`$I/base_b_neworacle.txt`에서 옮김). 모두 v.7 기대값에 대한 `AssertionError`이고, 자체 점검이 실패한 것은 없다.
- **채우기**: `sb_A2_pad40: padding moved the distance 0.0 -> 0.5176`, `sb_A2_pad7: … 0.0 -> 0.352`, `sb_B_padi: … 0.7532 -> 0.7725` 등 8가지 모두.
- **canal_open 몰아내기**: `padded clones crowded out B/C: [복제본 3개]`.
- **요약이 거리에 들어감**: `host words only in the summary moved the distance`, `B: host stuffed moved 0.7532`.
- **빈 H**: `sb_Acopy: 0.0 from a host without label/tag words`. 기대값은 1이다.
- **정확성**: `('1/6 = 2/12 = 6/36 (1/3)', [0.1835, 0.0, 0.0], Fraction(1, 3))`. 비율이 같아도 v.6에서는 거리가 서로 달랐다.
- **§9 숫자**: `B: 0.7532 vs reference 0.777778`. v5 테스트: `B and C tie on score and relevance -> subbrain_id ascending (sb_B)`.

원본 출력은 `$I/base_b_neworacle.txt`와 `$I/base_b_rerun{1,2,3}.txt`에 있다. 실패 목록은 `$I/base_b_failed_list.txt`, (c1)은 `$I/base_c1_matching_only.txt`, (d)는 `$I/base_d_unit.txt`에 있다.

## 5. 초록 결과

- 전체 **1656 passed** (13.5s, `umask 022`). 실패와 오류는 없다. oracle 772개, unit 884개다. 같은 실행을 세 번 더 했고 모두 1656 passed였다(`$I/green_reruns.txt`).
- 거리 관련 6개 파일(191개)은 `PYTHONHASHSEED` 0, 1, 12345에서 모두 통과했다.
- 1611에서 1656으로 45개가 늘었다. 내역:

| 파일 | 기준 `1641879` | 지금 | 차이 |
|---|---|---|---|
| `test_oracle_v7_matching.py` (신규) | 0 | 37 | +37 |
| `test_oracle_v6_matching.py` | 43 | 42 | −1 (§9 v.6 코사인 숫자 테스트 철회) |
| `test_unit_matching_distance.py` | 30 | 39 | +9 |
| 그 밖의 파일 | — | — | 개수는 같다(`test_oracle_v5_matching.py` 48, `test_unit_matching.py` 90, `test_unit_matching_exact_ties_v6.py` 15, `test_unit_service_v6.py` 10 등) |

## 6. 바뀐 기존 테스트와 근거 Oracle 줄

oracle 쪽은 테스트 작성자가, unit 쪽은 Builder가 바꿨다. 통합 담당은 세 가지를 직접 확인했다. 근거 줄이 매니페스트 v.7에 있다는 것, `git diff HEAD`의 테스트 이름과 단언이 아래 설명과 맞는다는 것, 그리고 "기준선" 열의 결과(§4 (b))다.

| 테스트 | 바뀐 것 | 근거 Oracle 줄 | 기준선 |
|---|---|---|---|
| `test_oracle_matching.py::test_must_m1_domain_distance` | import를 `_v7`로 바꿨다. B ≈ 0.75 → 7/9, D < 1 → D == 1 | §9 (v.7) "B·C 0.056, D·X 0". MUST-M5 "노드 라벨과 태그" | 빨강 |
| `test_oracle_matching.py`의 다양성 테스트 2개 | docstring과 주석만 바꿨다(B = C = 7/9). 단언은 그대로다 | MUST-M2 | 초록 |
| `test_oracle_v4_matching.py::test_must_m1_v4_diversity_swap_never_brings_in_a_below_tau_candidate` | import를 `_v7`로 바꿨다. docstring의 약한 후보 거리 8/9~1. "τ 미만은 뽑히지 않는다"는 단언은 그대로다 | MUST-M2 금지 결과 "가산점 때문에 τ 미만 후보가 선택됨" | 빨강 |
| `test_oracle_tiers.py` | 주석의 F 문서 숫자만 바꿨다(F 거리 7/9, 점수 ≈ 0.593, 여전히 A2 0.56보다 위). 논리는 그대로다 | MUST-T1, MUST-M2 | 초록 |
| `test_oracle_v5_matching.py` 손으로 만든 문서 | CLOSE_040·050·AT_TAU·060에 호스트 낱말 태그를 더했다(A의 36개 중 9개 이상 공유 → 거리 0). MID_040에는 호스트 태그 4개를 더했다(2/9, far_distance 미만). v.6에서는 요약이 이들을 가깝게 만들었는데 v.7은 요약을 세지 않기 때문이다. QK·QT·Q-01 관련도는 그대로라는 자체 점검이 있다 | MUST-M5 v.7 | 초록 (자체 점검) |
| `…::test_must_m2_v5_score_field_on_q01_matches_the_formula` | B 0.6260·C 0.6439 → 둘 다 0.40 + 0.3 × 7/9 | §9 (v.7), MUST-M2 | 빨강 |
| `…::test_must_m2_v5_q01_ranks_b_and_c_above_a2` | max_members 1에서 뽑히는 후보: C → B(정확한 동점이므로 subbrain_id) | MUST-M2 "(같으면 관련도, 그다음 subbrain_id 오름차순)", "Q-01은 B·C가 A2보다 위" | 빨강 |
| `…::test_must_m2_v5_full_tie_is_broken_by_subbrain_id_ascending` | 두 번째 자리: sb_C → sb_B | 같은 줄 | 빨강 |
| `…::test_must_m2_v5_distance_bonus_is_read_from_config` | 가산점 0.1에서 뽑히는 집합: {A2, C} → {A2, B} | MUST-M2 "`distance_bonus`(config)" | 빨강 |
| `…::test_must_m2_v5_match_explain_exposes_score` | B 점수 0.6260 → 0.6333 | MUST-M2 "응답에 후보별 `score`가 있다" | 빨강 |
| `…_equal_relevance_farther_field_ranks_higher`, `…_q02_keeps_a2_first` | 기준 구현이 `_v7`을 쓴다. 범위 표는 정확한 분수로 바꿨다(MID 2/9, AT_TAU 7/9, B 7/9, W_LABEL 8/9, W_SUB 1) | MUST-M2 "관련도가 같으면 먼 분야가 위다", §9 (v.5) Q-02 | 빨강 |
| `test_oracle_v6_matching.py::test_must_m5_reference_reproduces_the_oracle_section9_numbers` | **철회.** §9 (v.6) 코사인 숫자(0.34 / 0.75 / 0.81)를 확인하던 테스트다. v.7 후속은 `test_must_m5_v7_reference_reproduces_the_oracle_section9_numbers`다 | MUST-M5 v.7 정의 변경, §9 (v.7) | — |
| `…::test_must_m5_fixture_distances_from_host_a[Q-01,Q-02,Q-03]` | "B < C < D" → "B == C < D", D == 1 | §9 (v.7) | 빨강 ×3 |
| `…::test_must_m5_node_labels_tags_and_summaries_count[label,tag,summary]` | `…_node_labels_and_tags_count[label,tag]`로 이름을 바꾸고 summary를 뺐다. summary는 `test_must_m5_other_fields_do_not_count`의 매개변수로 옮겼다(5가지) | MUST-M5 "요약, 노드 유형, 엣지, 제목, 신고한 분야는 쓰지 않는다" | 빨강 ×3 |
| `…::test_must_m5_word_frequency_counts_not_just_presence` | `…_word_repetition_does_not_count`로 뒤집었다 | MUST-M5 "서로 다른 낱말의 집합" | 빨강 |
| `…::test_must_m5_words_come_from_textnorm_tokenize` | 불용어 확인 낱말을 요약에서 태그로 옮겼다(H가 비지 않도록) | MUST-M5 "`textnorm.tokenize`(조사 제거, 불용어 제거)" | 빨강 |
| `…::test_must_m5_content_change_changes_the_distance` | 요약을 지운 변형은 이제 B와 **같다**(예전에는 달랐다) | MUST-M5 | 빨강 |
| `…::test_must_m2_v6_q01_scores_and_order_follow_the_content_distance` | 순서 C, B, A2 → B, C, A2 | MUST-M2 동점 규칙 | 빨강 |
| `…::test_must_m2_v6_rounding_must_not_create_a_tie_that_relevance_breaks_the_wrong_way` | B·C가 비겨 예전 구성은 0으로 나누게 된다. 그래서 B + 유닛(2/3, id sb_B) 대 C(7/9)로 다시 만들었다 | MUST-M2 "순위 비교와 τ 비교는 반올림하지 않은 값으로 (v.6)" | 빨강 |
| `…::test_must_m2_v6_a_member_just_below_far_distance_does_not_satisfy_the_guarantee` | NEAR_060을 4/9로 다시 만들었다. AT_TAU_DOC이 7/9가 되어 "더 높은" 기준값을 0.6 → 0.8로 바꿨다 | MUST-M2 다양성 보장 `far_distance` | 빨강 |
| `…::test_must_m2_v6_canal_open_q01_expert_host_orders_members_by_score` | 기준 순서도 서버 sid로 동점을 처리한다. B·C(sid 순), 그다음 A2 | MUST-M2 동점 규칙 | 흔들림 (§4) |
| `tests/unit/test_unit_matching.py` | HS를 서로 다른 라벨 낱말 48개로 바꿨다(거리 = 1 − min(1, 공통/12)). `_shaped(shared=, fillers=)`. EXPECTED 값(0, 1/3, 1/2, 3/4, 1)은 그대로다 | MUST-M5 v.7 | 빨강 14 (§4 (d)) |
| `tests/unit/test_unit_matching_distance.py` | 새로 썼다(30 → 39개). §9 (v.7) 값, 독립 기준, 채우기, 요약·유형·엣지·제목·분야 제외, 빈 H, 해시 시드 등 | MUST-M5 v.7 | 빨강 34 |
| `tests/unit/test_unit_matching_exact_ties_v6.py` | 같은 네 가지 동점 성질을 k/n 구성으로 다시 만들었다. 무리수(제곱근) 처리 코드는 지웠다 | MUST-M2, MUST-M5 v.7 | 빨강 15 |
| `tests/unit/test_unit_service_v6.py` | B·C가 정확히 비겨 "반올림하면 순서가 틀어진다" 시나리오가 성립하지 않는다. 그래서 B를 호스트 낱말 하나(공차)를 더한 판으로 올려 거리 2/3으로 만들고, TINY_BONUS를 0.0001로 바꿨다. 기대 순서 [A2, C, B]는 그대로다 | MUST-M2 (v.6 반올림 조항) | 빨강 1 |

**Oracle과 어긋나는 oracle 테스트는 찾지 못했다.** 772개 모두 초록이다. 각 단언의 근거 줄이 v.7 매니페스트에 있다는 것도 위 표대로 확인했다. 테스트 작성자가 일부러 고정하지 않은 것도 있다. §10 "관련도 낱말 채우기"(관련도 스터핑)이다. 채우기 테스트의 자체 점검은 채운 낱말이 질의어와 겹치지 않는지 확인한다. 그래서 관련도는 움직이지 않는다.

## 7. 스모크 — `match-explain`

`zsh $I/smoke.sh $I r1`(두 번째는 `r2`). `umask 022`인 새 scratch 디렉터리에서 실제 콘솔 스크립트(`.venv/bin/opencanal`)를 돌렸다. 순서는 `init-db` → `seed-fixtures`(fixture 7개, 사용자 6명) → `set-tier user_a pro` → `match-explain` Q-01, Q-02다. 호스트는 A의 subbrain_id다. 출력은 `$I/smoke_out_r{1,2}.txt`에 있다. 토큰은 출력, scratch 파일, 이 문서 어디에도 적지 않았다(`oc_` 평문 0건 확인). 백업·복원은 이번 변경과 관계가 없어 돌리지 않았다.

### 7.1 Q-01 "모듈러 건축의 현장 조립 오류를 줄일 아이디어" (user_a, Pro, 호스트 A, max_members 6)

`query_mode_used: topic`, `strategy: relevance_with_distance_bonus`, `tau: 0.2000`, `query_terms: 모듈러, 건축, 현장, 조립, 오류`, `truncated: False`. 1회차 값이다.

| rank | fixture | subbrain_id | 제목 | relevance | distance | score | matched_terms | selected | reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | C | sb_1a30ead86fb521ff | 단백질 자기조립과 오류 교정 | 0.4000 | 0.7778 | 0.6333 | 조립, 오류 | yes | selected_score |
| 2 | B | sb_753c0ddb2d5252c0 | 퍼즐 게임 블록 설계 원칙 | 0.4000 | 0.7778 | 0.6333 | 조립, 오류 | yes | selected_score |
| 3 | A2 | sb_167a102c9dffd852 | 목조 모듈러 주택 설계 메모 | 0.5600 | 0.0000 | 0.5600 | 모듈러, 건축, 현장 | yes | selected_score |
| 4 | X | sb_21fe2f5f5dbe0f83 | 사내 보안 점검 체크리스트 | 0.0000 | 1.0000 | 0.0000 | | no | below_tau |
| 5 | D | sb_a27543b8a0f12e58 | 동네 빵집 단골 만들기 | 0.0000 | 1.0000 | 0.0000 | | no | below_tau |

- **MUST-M2 "기본값으로 Q-01은 B·C가 A2보다 위다"**: 성립한다(0.6333 > 0.5600).
- **B·C는 정확히 비긴다.** 거리 7/9, 관련도 0.40, 점수 19/30이 모두 같다. 그래서 순서는 subbrain_id 오름차순이다. 1회차는 sb_1a30…(C) < sb_753c…(B)라 C가 위였다. 2회차도 sb_6fec…(C) < sb_9be8…(B)라 C가 위였다. 서버 id는 무작위이므로 실행에 따라 B가 위일 수 있다. v.6에서는 C(0.8131)가 B(0.7532)보다 내용상 멀어 늘 C가 위였다.
- **D·X도 정확히 비긴다**(거리 1, 관련도 0, 점수 0). 1회차는 X(sb_21fe…)가, 2회차는 D(sb_37de…)가 위였다. 모두 sid 순이다. v.6에서 D는 요약의 우연한 공통 낱말 때문에 0.9755였다. v.7은 요약을 세지 않으므로 1이다. §6.1 "D … 호스트 A 태그를 하나도 공유하지 않는다"와 맞는다.
- 2회차의 숫자(관련도·거리·점수·선택·이유)는 1회차와 모두 같다.

### 7.2 Q-02 "내 두뇌를 평가해줘"

`query_mode_used: whole_host`(호스트 태그·라벨 용어 36개), `truncated: False`. 1회차 값이다.

| rank | fixture | relevance | distance | score | matched_terms | selected | reason |
|---|---|---|---|---|---|---|---|
| 1 | A2 | 1.0000 | 0.0000 | 1.0000 | 모듈러, 건축, 현장, 품질, 상세, 시공, 치수, bim, 공장, 모듈, 관리, 유닛 | yes | selected_score |
| 2 | C | 0.4500 | 0.7778 | 0.6833 | 조립, 오류, 유닛 | yes | selected_score |
| 3 | B | 0.4000 | 0.7778 | 0.6333 | 조립, 오류 | yes | selected_score |
| 4 | X | 0.0000 | 1.0000 | 0.0000 | | no | below_tau |
| 5 | D | 0.0000 | 1.0000 | 0.0000 | | no | below_tau |

- §9 (v.5) "주제 없는 질의(Q-02)에서는 A2(1.00)가 여전히 위다"와 맞다. MUST-M3에 따라 D는 빠진다.
- C의 겹친 용어 "유닛"은 관련도(MUST-M1, 요약 포함)에서만 센다. C 요약에 "서브유닛"이 두 번 나온다. 거리의 공통 낱말은 {조립, 오류} 둘뿐이다(§7.3). 관련도와 거리가 보는 필드가 다르다는 것이 표에서 그대로 보인다.

### 7.3 독립 계산 대조

`$I/indep_check.py`. `matching.py`와 `_v7.py`를 쓰지 않고, `textnorm.tokenize`, config, fixture JSON만으로 짰다(26줄). 출력은 `$I/indep_check_out.txt`에 있다.

| fixture | \|C\| | \|H ∩ C\| | 유사도 | 거리 | 공통 낱말 |
|---|---|---|---|---|---|
| A2 | 34 | 10 | 5/18 (0.278) | 0 | (10개) |
| B | 35 | 2 | 1/18 (0.056) | 7/9 (0.7778) | 오류, 조립 |
| C | 27 | 2 | 1/18 (0.056) | 7/9 (0.7778) | 오류, 조립 |
| D | 34 | 0 | 0 | 1 | — |
| X | 27 | 0 | 0 | 1 | — |
| P (비공개, 후보 아님) | 29 | 5 | 5/36 (0.139) | 4/9 (0.4444) | — |

\|H(A)\| = 36, saturation 1/4, bonus 3/10. 점수(관련도는 표의 값): Q-01 A2 0.5600, B 0.6333, C 0.6333 / Q-02 A2 1.0000, B 0.6333, C 0.6833. §7.1·§7.2 표, 그리고 §9 (v.7) "A2 0.278, B·C 0.056, D·X 0"과 모두 같다.

## 8. 채우기 공격 재실행 (M5-PAD-1)

v.6 적대 검토의 두 재현 스크립트를 `$I/padding/`에 복사해 고쳤다. 공격 입력(채우기 노드 = 라벨 "쿼쿼" + 같은 태그 20개, 복제본 핵심 = "모듈러 건축"·"현장" 노드 2개)은 원본 그대로다. 고친 것은 세 가지다.
- src 경로를 `OC_SRC`로 받는다. 같은 스크립트를 v.6 코드(`git archive 1641879 src`)와 작업 트리 코드에 모두 돌렸다. 매번 `opencanal.__file__`이 의도한 경로인지 단언한다.
- 원본 `exp1_padding.py`의 마지막 `assert`는 공격이 **성공한다**(채운 복제본 3개가 3자리를 모두 차지한다)고 단언했다. 이것을 "채우기 전과 후 비교"로 바꿨다. 종료 코드는 바뀐 항목 수다.
- `e2e_padding.py`는 임시 디렉터리를 scratch(`$I/padding/tmp`) 아래에 만든다. 멤버마다 relevance·distance를 함께 기록하고, 채운 실행을 채우지 않은 실행과 비교한다.

### 8.1 `exp1_padding.py` (`matching.match_with_ranking` 직접 호출, Free 3자리)

| 확인 | v.6 코드 | v.7 (작업 트리) |
|---|---|---|
| A2 + 채우기 노드 1개, 거리 | 0 → 0.2034 | 0 → **0** |
| A2 + 2개 | 0 → 0.5379 (먼 후보가 됨) | 0 → **0** |
| A2 + 5개 | 0 → 0.8055 | 0 → **0** |
| Q-01 max_members 1, A2 + 5개 | 선택 {C} → {A2} (A2 점수 0.56 → 0.8016) | {B} → **{B}** (B·C 동점, sb_B < sb_C) |
| 같은 분야 복제본 3개, 채우기 전과 후 선택 | {C, B, Z0} → {Z0, Z1, Z2} (거리 0 → 0.9411, 점수 0.6 → 0.8823) | {Z0, Z1, Z2} → **{Z0, Z1, Z2}** (거리 5/9, 점수 0.7667 그대로) |
| 바뀐 항목 수 (종료 코드) | **7** | **0** |

### 8.2 `e2e_padding.py` (`subbrain_import` → 공개 → `canal_open`, user_a Free, 호스트 A, Q-01)

| 실행 | v.6 코드 멤버 (relevance, distance) | v.7 멤버 (relevance, distance) |
|---|---|---|
| 채우기 없음 | C (0.4, 0.8131), B (0.4, 0.7532), A2 (0.56, 0.0) | C (0.4, 0.7778), B (0.4, 0.7778), A2 (0.56, 0.0) |
| A2 + 2개 | **A2 (0.56, 0.5379)**, C, B — 바뀜 | B, C, A2 (0.56, **0.0**) — 같음 |
| A2 + 5개 | **A2 (0.56, 0.8055)**, C, B — 바뀜 | B, C, A2 (0.56, **0.0**) — 같음 |
| 복제본 3개, 채우기 없음 | C, B, Z2 (0.6, 0.0) | Z1, Z2, Z0 (0.6, 0.5556) |
| 복제본 3개 + 3개씩 채움 | **Z2, Z1, Z0 (0.6, 0.9411)** — 바뀜 | Z0, Z2, Z1 (0.6, **0.5556**) — 같음 |
| 바뀐 비교 수 (종료 코드) | **3** | **0** |

v.7에서는 채우기가 거리, 점수, 선택을 하나도 바꾸지 않는다. 같은 점수의 B·C와 복제본끼리의 순서는 실행마다 다를 수 있다. 서버가 만드는 무작위 subbrain_id 순이기 때문이다. 비교는 멤버 집합과 각 멤버의 값으로 했다. 출력은 `$I/padding/{exp1,e2e}_{v6,v7}.txt`에 있다.

**주의 — 채우지 않은 복제본 행.** v.7에서는 채우지 않은 복제본 3개가 이미 Free 3자리를 모두 차지한다. v.6에서는 B·C가 남았다. 채우기와는 관계없다(채우기 전과 후가 같다). 원인은 v.7 정의 자체에 있고, §9 해석 1에 적었다.

## 9. 해석 — 오너 확인이 필요한 것

1. **작은 같은 분야 후보가 "먼 분야"로 보인다 (낱말 줄이기).** 유사도의 분모가 호스트 낱말 수(\|H\|)다. 그래서 호스트와 같은 분야여도 호스트 낱말을 적게 가진 작은 후보는 거리가 크다. 호스트 A(36개)에서 거리 ≥ `far_distance` 0.5가 되려면 공통 낱말이 4개 이하(36 × 0.125)면 된다. 이런 후보는 가산점을 받고, 다양성 보장의 "먼 후보" 자리도 채운다. 측정한 값(`$I/padding/shrink_{v6,v7}.txt`, `shrink_sweep_v7.txt`):

   | 후보 = A의 낱말 k개만 가진 노드들 | k=1 | 2 | 3 | 4 | 5 | 6 | 8 | 9 이상 |
   |---|---|---|---|---|---|---|---|---|
   | v.6 거리 | 0.6282 | 0.4742 | 0.3560 | 0 | 0 | 0 | 0 | 0 |
   | v.7 거리 | 0.8889 | 0.7778 | 0.6667 | 0.5556 | 0.4444 | 0.3333 | 0.1111 | 0 |

   - e2e 복제본은 낱말 4개(모듈러·건축·프리패브·현장)를 가진다. 모두 A의 낱말이고, 그중 질의어는 3개다. v.7 결과는 관련도 0.60, 거리 5/9, 점수 0.7667이다. 이 값이 B·C의 0.6333을 넘는다. 그 결과 복제본 셋이 Free 3자리를 모두 차지하고, 다양성 보장도 작동하지 않는다. 복제본 자신이 먼 후보이기 때문이다.
   - 라벨에만 질의어 3개를 둔 복제본은 관련도가 0.48이다. 이 경우 k = 4이면 셋이 모든 자리를 차지하고, k = 5~6이면 B·C와 복제본 하나가 뽑힌다. k ≥ 7이면 A2·B·C로 돌아간다.

   MUST-M5의 금지 결과는 "낱말 **채우기·반복**으로 거리를 키울 수 있음"이다. 낱말을 **덜어** 거리를 키우는 것은 적혀 있지 않다. 그래서 Oracle 위반은 아니고 테스트도 없다. 테스트 작성자의 몰아내기 테스트는 A2 전체를 복제한 거리 0 복제본을 쓴다. §10 "관련도 낱말 채우기"와 함께 오너가 정할 일이다. 그대로 둘지, 가산점에 조건을 더할지를 정해야 한다. 다만 후보 쪽 크기나 비율로 거는 조건은 후보가 낱말을 덧붙여 맞출 수 있다. 그런 조건은 v.7이 막은 채우기 수단을 다시 열 수 있다. 통합 단계에서는 고치지 않았다.
2. **`distance_saturation` ≤ 0.** Builder는 "공통 낱말이 하나라도 있으면 거리 0, 없으면 1"이라는 v.6 규칙을 남겼다. 매니페스트의 식은 saturation이 0일 때 정의되지 않는다. config 값은 0.25라서 지금은 쓰이지 않는 경로다.
3. **비대칭.** v.7 거리는 호스트 기준이라 `content_distance(h, c)`와 `content_distance(c, h)`가 다를 수 있다. MUST-M5 문장("호스트 낱말 중")대로다. Builder는 docstring의 "Symmetric"을 지웠다.
4. **"호스트는 커널에 쓰는 버전".** CHANGE-005 §9.4와 같다. canal_open은 공개 버전, match_explain은 공개 상태면 공개 버전·아니면 최신 버전을 쓴다. v.7에서 바뀐 것은 없다.
5. **B·C 동점이 Q-01의 기본 상태가 됐다.** "B·C가 A2보다 위"는 성립한다. 하지만 B와 C 중 무엇이 위인지는 무작위 서버 id가 정한다. 2자리 이상이면 둘 다 들어가므로(둘 다 A2보다 위) 결과 집합은 같고, 커널 안의 순서만 id를 따른다. 1자리로 자를 때만 어느 쪽이 남는지가 id에 달린다.
6. **매니페스트 안의 v.6 숫자.** §9 (v.6) 행에는 아직 "A–A2 코사인 0.34", "B·C(거리 약 0.75·0.81)"가 있다. v.7 숫자는 §9 (v.7) 행에 있으므로 모순은 아니다(행마다 버전이 붙어 있다). 다만 v.6 행만 읽으면 지금 값과 다르다. 매니페스트는 고정 파일이라 고치지 않았다.

## 10. 남은 위험

| 위험 | 내용 | 정도 |
|---|---|---|
| 낱말 줄이기 | §9 해석 1. 같은 분야의 작은 서브브레인(호스트 낱말 4개 이하)이 먼 분야 가산점과 먼 후보 자리를 얻는다. 같은 주제의 작은 서브브레인을 여러 사용자가 올리면 진짜 먼 분야(B·C)가 Free 커널에서 밀려난다. 채우기와 달리 Oracle이 막지 않는다 | 중간 (오너 결정 대기) |
| 관련도 낱말 채우기 | §10 행 그대로다. 질의에 자주 나올 낱말을 태그로 붙여 관련도 τ를 넘길 수 있다. v.7은 거리 조작만 막았다 | 중간 (오너 결정 대기, v.7 범위 밖) |
| 고정 파일의 낡은 주석 | `src/opencanal/config.py` 28행 "cosine / distance_saturation". 동작에는 영향이 없다. TASK 갱신으로 고친다 | 낮음 |
| 표시 순서 | Q-01 표에서 B·C(그리고 D·X)는 같은 숫자로 보인다. 순위는 무작위 id 순이라 실행마다 바뀔 수 있다. 규칙대로이지만 사용자는 임의로 느낄 수 있다 | 낮음 |
| 거리 계산 비용 | 호출마다 모든 후보의 낱말 집합을 새로 만든다(캐시 없음). v.6과 같은 구조이고, 빈도 벡터 대신 집합이라 조금 가볍다 | 낮음 (R0 규모) |
| 기준선 판별력 | §4의 흔들리는 1건은 v.6에서 약 절반 확률로 통과한다. 다른 테스트가 늘 같은 사실을 잡는다 | 낮음 |
| 오너 확인 대기 | `distance_saturation` 0.25와 `far_distance` 0.5는 v.6에서 코사인 기준으로 고른 값이다(§9 (v.6)). v.7의 겹침 비율에도 같은 값을 쓴다. 해석 1의 "4개 이하면 먼 후보"는 이 두 값에서 나온다 | — |

## 11. 동시 편집 확인

통합을 시작할 때 수정·미추적 파일과 `src/opencanal/*.py`의 해시를 떠 두었다(`$I/hashes_start.txt`, 26개). 스모크와 재실행을 마친 뒤 다시 비교했다(`$I/hashes_now.txt`). 달라진 것은 통합 담당이 고친 `src/opencanal/service.py`와, 수정 목록에 새로 들어온 `README.md`뿐이다. 그 밖의 해시는 그대로다. 그동안 다른 에이전트는 파일을 바꾸지 않았다. `git worktree list`에는 본 작업 트리만 있고, `git stash list`는 비어 있다.
