# CHANGE-005 — Oracle v.6 통합 기록 (거리는 내용으로, 반올림 전 비교, 백업 임시 파일 0600)

> NDSH 부록 B-7 양식. 통합 담당(Integrator)이 2026-10-06에 남긴 기록이다. 사실만 적는다.
> 기준 문서는 `docs/oracle/ORACLE_MANIFEST.md` v2026-10-06.6이다. 그중 §2 오너 결정 "거리는 누가 정하나", MUST-M5, MUST-M2 (v.6 문장), MUST-E3 (v.6 문장), §9 "(v.6)" 행을 따른다. 기준 커밋은 `c817d43`이며, 이번 작업은 커밋하지 않았다.
> 작업 파일 위치: `$V`는 이 세션 scratchpad의 `v6/`, `$I`는 `$V/integrator/`다. 둘 다 저장소 밖에 있다. 기준선 worktree는 `$V/integ-base`에 만들었다가 지웠다.

## 1. 오너 결정과 반영

| # | 오너 결정·기준 | Oracle 줄 | 구현 반영 | 고정한 테스트 |
|---|---|---|---|---|
| 1 | 거리는 누가 정하나 → **내용으로 계산 (신고 분야 대신)** | §2 "거리는 누가 정하나 \| 내용으로 계산 (신고 분야 대신) \| MUST-M5 (v.6)". MUST-M5 "거리 = 1 − min(1, 유사도 ÷ `distance_saturation`)". §9 (v.6) `distance_saturation` = 0.25 | `matching.content_distance`가 노드 라벨·태그·요약 낱말 빈도 벡터의 코사인으로 거리를 계산한다. 낱말은 `textnorm.tokenize`로 뽑고, config의 조사·불용어 설정을 쓴다. 제목·`domains`·엣지 요약·노드 type은 쓰지 않는다. 어느 한쪽에 낱말이 없으면 거리는 1.0이다. 호스트 벡터는 `match()` 한 번에 한 번만 만든다. `domain_distance`는 지웠다 (Builder M) | `test_oracle_v6_matching.py` 중 MUST-M5 테스트, `test_unit_matching_distance.py` 30개 |
| 2 | 반올림 전 값으로 비교 | MUST-M2 "순위 비교와 τ 비교는 **반올림하지 않은 값**으로 하고, 반올림은 응답에 보일 때만 한다 (v.6)". §9 (v.6) "두 번 반올림하면 점수 순서와 관련도 동점 처리가 틀어졌다" | 관련도와 점수는 정확한 분수(`Fraction`)로 계산한다. config 숫자는 적힌 십진수 그대로 읽는다(`Fraction(str(x))`). 순위와 τ 비교는 모두 이 값으로 한다. `MatchCandidate`의 relevance·distance·score는 표시할 때만 소수 넷째 자리로 반올림한다 (Builder M). 통합 단계에서 service와 CLI도 같은 원칙을 따르게 했다 (§2.1) | `test_oracle_v6_matching.py` 중 MUST-M2 v.6 테스트, `test_unit_service_v6.py` 10개 |
| 3 | 다양성 보장의 "먼 후보" | MUST-M2 "거리가 `far_distance`(config) 이상인 자격 후보가 있는데 선택에 하나도 없으면 가장 좋은 것을 넣는다". §9 (v.6) `far_distance` = 0.5 | `_guarantee_diversity`는 `distance >= cfg.far_distance`를 먼 후보로 본다. 기본 전략과 `relevance_plus_diversity`에 모두 적용한다 (Builder M) | 같은 파일의 diversity 테스트 4개, v5 diversity 테스트 |
| 4 | 백업 임시 파일 0600 | MUST-E3 "백업·복원 중 잠깐 만드는 평문 임시 파일도 0600이고 작업이 끝나면 지운다 (v.6)". §9 (v.6) "백업이 평문 DB 사본을 0644로 잠깐 만들었다 (적대 검토 E3-3)" | `Store.snapshot_bytes`는 sqlite backup API로 비공개 `:memory:` DB에 복사한 뒤 `serialize()`로 바이트를 읽는다. 디스크에는 파일을 만들지 않는다. WAL 표시가 남은 헤더 바이트 18/19(`\x02\x02`)는 `\x01\x01`로 고친다. serialize가 없는 SQLite에서는 0700 디렉터리 안에 0600 파일을 만들어 쓰고 지운다. 복원은 원래 `mkstemp`(0600)를 쓰고 `finally`에서 지우고 있었으므로 코드는 그대로 두었다 (Builder E3) | `test_oracle_v6_file_modes.py` 7개, `test_unit_store_e3_v6.py` 13개, `test_unit_cli_backup_e3_v6.py` 6개 |

표의 구현 세부는 **빌더 보고**에서 옮겼다. 해당 값은 `Fraction` 사용, 헤더 바이트 패치, serialize 대체 경로다. 통합 담당이 직접 확인한 것은 다섯 가지다.
- §4 빨강 기준선 50건이 지금은 모두 초록이다.
- §4 분리 실행으로 매칭 47건과 E3 3건이 각각 어느 파일의 변경으로 초록이 되는지 확인했다.
- §8 스모크의 거리·점수가 §9 숫자, 그리고 통합 담당이 따로 짠 계산(§8.3)과 일치한다.
- §8 스모크에서 TMPDIR에 아무 파일도 생기지 않았다.
- 복원한 DB의 `journal_mode`, `quick_check`, 행 수를 확인했다.

## 2. 변경 요약

병렬 단계에서는 세 명이 작업했다.
- **테스트 작성자**: `tests/oracle`에 새 파일 4개(`_v6.py`, `_tmpspy.py`, `test_oracle_v6_matching.py`, `test_oracle_v6_file_modes.py`)를 만들고, 기존 파일 4개를 고쳤다.
- **Builder M**: `matching.py`와 그 단위 테스트를 맡았다.
- **Builder E3**: `store.py`, `cli.py`(docstring만)와 그 단위 테스트를 맡았다.

통합을 시작할 때 작업 트리는 이미 **1586 passed**였다(oracle 736, unit 850). 빌더들이 보고한 숫자(1521 passed / 15 failed, 1488 passed)는 서로의 변경이 들어오기 전 시점의 값이다. 그래서 통합 단계에서 고친 것은 실패한 테스트가 아니다. Builder M이 남긴 메모의 service·CLI 호출 지점이고, 이 지점들은 아직 반올림한 값으로 순위를 매기거나 τ와 비교하고 있었다.

### 2.1 통합 단계에서 직접 바꾼 것

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/opencanal/service.py` `_canal_open` | `matching.match()` 대신 `matching.match_with_ranking()`을 부른다. 멤버는 `ranking` 순서(반올림 전 정확한 순위)로 나열하고, `c.selected`인 후보만 쓴다. 반올림된 `c.relevance >= result.tau`를 다시 검사하던 코드는 지웠다. 저장되는 커널 멤버 순서도 같은 순위를 따른다 | 원인 둘. (1) `in_rank_order`가 반올림한 필드로 정렬했다. 두 점수가 같은 값으로 반올림되면 멤버 순서가 `match()`가 실제로 고른 순서와 달라지고 subbrain_id(무작위)로 정해졌다. (2) τ = 0.33333일 때 관련도가 정확히 1/3인 멤버는 `match()`에서는 자격이 있다. 그런데 표시값 0.3333 < τ라서 canal_open이 그 멤버를 버렸다. 남은 멤버가 없으면 `NO_RELEVANT_SUBBRAIN`으로 끝났다. 근거는 MUST-M2 "순위 비교와 τ 비교는 반올림하지 않은 값으로". oracle의 τ 테스트는 `match()`만 거치므로 이 경로는 잡지 못했다 |
| `src/opencanal/service.py` `_subbrain_search` | τ 비교와 정렬은 반올림 전 관련도로 한다. 응답의 `relevance`만 `matching.display_value`(소수 넷째 자리)로 바꿨다 | `score_relevance`가 이제 반올림하지 않은 float를 돌려준다(Builder M). 그대로 두면 응답에 0.3333333333333333이 나간다. MUST-M2 "반올림은 응답에 보일 때만" |
| `src/opencanal/service.py` `_match_explain` | `match_with_ranking`을 쓰고, 응답 최상위에 `ranking`(`[{subbrain_id, version}, …]`, 전략의 정확한 순위)을 더했다. `candidates`는 models.py 계약대로 관련도 순 그대로다 | 오너가 기준을 연구할 때 보는 표(§2 self-test 2)가 실제 순위와 어긋나지 않게 하려는 것이다. 반올림된 필드로는 정확한 순위를 다시 만들 수 없다. subbrain_id는 서버가 만든 값이고 `candidates`에 이미 봉투 밖으로 나가 있으므로, NEVER-09 범위는 늘지 않는다 |
| `src/opencanal/service.py` 도구 설명·주석 | match_explain 설명의 "도메인 거리 / domain distance"를 "내용 거리, 점수, ranking"으로 바꿨다. canal_get의 두 주석(호스트에서 나온 거리, 보이는 멤버의 순서가 드러내는 정보)도 v.6에 맞게 고쳤다 | MUST-M5. tools/list에 나가는 설명 문구가 틀려 있었다. 이 문구를 고정한 테스트는 없다(grep으로 확인) |
| `src/opencanal/cli.py` `match-explain` | `_in_rank_order`는 envelope의 `ranking`이 후보 목록과 정확히 맞으면 그 순서를 쓴다. 맞지 않으면(없음, 중복, 개수 다름) 예전처럼 반올림한 필드로 정렬한다. relevance·distance·score 칸과 머리의 `tau`는 소수 넷째 자리로 보인다(`_shown_number`, 예전에는 셋째 자리) | 표의 순위 열이 실제 선택과 어긋나지 않게 했다. 예전처럼 셋째 자리로 보이면 서버가 넷째 자리로 반올림한 값을 한 번 더 반올림하게 된다. 기존 CLI 테스트의 `"0.700" in row` 같은 단언은 "0.7000"에서도 성립한다 |
| `tests/unit/test_unit_service_v6.py` (신규, 10개) | τ = 0.33333에서 1/3 멤버 유지, τ = 0.26667에서 0.2667로만 보이는 후보 제외, search 표시 반올림, 반올림하면 같아지는 B·C 점수에서 멤버 순서가 정확한 순위를 따름(B의 id가 C보다 앞서도록 다시 뽑는다), match_explain `ranking`과 CLI 표 순서, `ranking`이 맞지 않을 때 대체 경로, 넷째 자리 표시 | 위 변경을 고정한다. τ와 distance_bonus는 `model_copy`로만 바꾼다. config/는 건드리지 않는다 |
| `README.md` | match-explain 설명에 내용 거리와 "순위·τ 비교는 반올림 전, 표는 넷째 자리"를 더했다. 백업·복원 설명에 임시 파일 처리를 더했다 | 사용자가 보는 설명을 실제 동작에 맞췄다 |
| `evidence/CHANGE-005.md` (신규) | 이 문서 | |

고정 파일(`docs/`, `config/`, `fixtures/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. `git diff HEAD --stat -- docs config fixtures src/opencanal/models.py src/opencanal/textnorm.py src/opencanal/config.py pyproject.toml`의 출력은 비어 있다. `tests/oracle`의 변경은 모두 테스트 작성자가 했다.

통합을 시작할 때 수정·미추적 파일 15개의 해시를 떠 두었다(`$I/hashes_start.txt`). 끝에 다시 비교했을 때 달라진 것은 통합 담당이 고친 파일뿐이었다. 해시가 바뀐 `cli.py`, 수정 목록에 새로 들어온 `service.py`·`README.md`, 새 파일 `test_unit_service_v6.py`다. 그동안 다른 에이전트는 파일을 바꾸지 않았다. 스키마 변경은 없다.

## 3. 실행 명령

```bash
# 자동 검사 (저장소 루트)
umask 022; .venv/bin/python -m pytest -q -p no:cacheprovider

# 빨강 기준선 (저장소 밖 worktree)
git worktree add --detach $V/integ-base c817d43
cp tests/oracle/{_v6.py,_tmpspy.py,test_oracle_v6_matching.py,test_oracle_v6_file_modes.py,\
test_oracle_v5_matching.py,test_oracle_matching.py,test_oracle_v4_matching.py,test_oracle_tiers.py} $V/integ-base/tests/oracle/
cd $V/integ-base && export PYTHONPATH=$V/integ-base/src && umask 022
<repo>/.venv/bin/python -m pytest -q -p no:cacheprovider tests/oracle -rf      # (b) 새 oracle 파일
cp <repo>/src/opencanal/matching.py src/opencanal/ ; pytest tests/oracle ; git checkout -- src  # (c1)
cp <repo>/src/opencanal/{store,cli}.py src/opencanal/ ; pytest tests/oracle ; git checkout -- src # (c2)
git stash -u; pytest; git stash drop                                          # (a) 커밋된 테스트 그대로
git worktree remove --force $V/integ-base && git worktree prune

# 통합 변경 사보타주: $I/mut_s1..s5 (src 사본 + 변이 하나)
OPENCANAL_CONFIG_DIR=<repo>/config .venv/bin/python -m pytest -q -o pythonpath=$I/mut_sN/src tests/unit/test_unit_service_v6.py

# 스모크: zsh $I/smoke.sh $I   (출력 $I/smoke_out.txt, 토큰은 가렸다)
```

참고 사항 셋.
- **(a)의 stash.** `git stash`의 ref는 worktree끼리 공유된다. 그래서 실행 전후로 `git stash list`가 비어 있는지, 본 작업 트리의 해시가 그대로인지 확인했다.
- **기준선 import 경로.** worktree에서는 `pyproject.toml`의 `pythonpath = ["src"]`가 worktree 자신의 src를 가리킨다. `import opencanal`이 worktree 경로를 찍는 것도 확인했다. CLI 하위 프로세스는 export한 `PYTHONPATH`를 물려받는다. 스파이용 `sitecustomize`는 이 값을 지우지 않고 앞에 덧붙인다(`_spy_env`). 그래서 CLI 백업 테스트도 기준선 코드를 실행했다.
- **사보타주 실행.** 저장소 안에서 돌릴 때는 `pyproject`의 `pythonpath`가 `PYTHONPATH`보다 앞선다. 그래서 `-o pythonpath`로 덮었다. 처음 시도에서는 사본에 config가 없어 모든 변이가 같은 이유로 실패했다. `OPENCANAL_CONFIG_DIR`을 주고 다시 돌렸고, 그 결과만 §7에 적었다.

## 4. 빨강 기준선

| 실행 | 결과 | 해석 |
|---|---|---|
| (a) `c817d43` 그대로 (커밋된 테스트) | **1469 passed** | 작업 지시와 같다. v.6을 아직 구현하지 않았고 테스트도 없었다 |
| (b) (a)에 새·수정 oracle 파일 8개 (tests/oracle 736개) | **50 failed, 686 passed** | 파일별: v6_matching 33, v5_matching 12, v6_file_modes 3, matching 1, v4_matching 1. 테스트 작성자 보고(50 failed, 685 passed + `test_must_e1_key_location_is_gitignored` 1건)와 같다. 그 1건은 작성자의 scratch 사본에 `.gitignore`가 없어서 생겼고, 실제 worktree에서는 통과했다. 같은 실행을 세 번 더 했고, 세 번 모두 같은 50건이었다 |
| (c1) (b)에 작업 트리 `matching.py`만 넣음 | 3 failed, 733 passed | 남은 3건은 모두 MUST-E3 v.6이다. 따라서 매칭 47건은 `matching.py`만으로 초록이 된다 |
| (c2) (b)에 작업 트리 `store.py`·`cli.py`만 넣음 | 46 failed, 690 passed | E3 3건이 초록이 됐다. 매칭 1건(`test_must_m2_v6_canal_open_q01_expert_host_orders_members_by_score`)도 이번에는 우연히 통과했다. 아래 참고 |

기준선 실패의 내용(실패 메시지에서 옮김):
- **MUST-E3 v.6 (3건)** — `snapshot_bytes`(파일 DB와 `:memory:`)와 CLI `backup`이 TMPDIR 아래 `opencanal-snap-*/snapshot.db`(와 `-journal`)를 **0o644**로 만들었다. 실패 메시지: `plaintext DB file(s) seen with a mode other than 0600 (MUST-E3 v.6): {…/snapshot.db: ['0o644']}`
- **MUST-M5 (거리)** — 신고 분야만 바꿔도 A2의 거리가 1.0이 됐다(`domains ['architecture'] moved A2 to 1.0` 등 4건). 같은 제목·분야이고 공통 낱말이 없는 후보가 거리 1이 아니었다. 고정 fixture 거리가 기준값과 달랐다. 예: v4 약한 후보의 기대값은 0.8177인데 1.0이 나왔다.
- **MUST-M2 v.6 (반올림)** — τ = 0.26667에서 L·T가 둘 다 뽑혔다. 기대는 T만이다. τ = 0.33333에서는 아무것도 뽑히지 않았다. 기대는 T다. 관련도가 같을 때 내용상 더 먼 C가 B보다 위에 오지 않았다.

**기준선에서 흔들린 테스트 1건.** `test_must_m2_v6_canal_open_q01_expert_host_orders_members_by_score`는 v.5에서 B와 C가 0.70으로 비긴다. 그래서 순서가 무작위 subbrain_id로 정해진다. 기준선에서 이 테스트만 따로 12번 돌렸더니 7번 통과, 5번 실패했다. 전체 실행 네 번에서는 모두 실패했다. 이 테스트 하나만으로는 v.5와 v.6을 확실히 가르지 못한다. 다만 같은 사실을 결정적으로 확인하는 테스트가 따로 있다. `test_must_m2_v6_q01_scores_and_order_follow_the_content_distance`와 `test_must_m2_v6_match_explain_scores_use_the_content_distance`는 기준선에서 늘 빨강이다. 통합 단계의 `test_canal_open_members_follow_the_exact_ranking_when_scores_round_alike`는 id 순서를 다시 뽑아서 이런 우연을 없앴다.

전체 실패 목록은 `$I/base_failed_list.txt`, 원본 출력은 `$I/base_neworacle.txt`에 있다.

## 5. 초록 결과

- 전체 **1596 passed** (12.1s, `umask 022`). 실패와 오류는 없다. oracle 736개, unit 860개다.
- 통합 전 작업 트리는 1586 passed였다. 늘어난 10개는 `test_unit_service_v6.py`다.
- 새·바뀐 파일별 개수:

| 파일 | 개수 |
|---|---|
| `test_oracle_v6_matching.py` | 43 |
| `test_oracle_v6_file_modes.py` | 7 |
| `test_oracle_v5_matching.py` | 48 |
| `test_unit_matching.py` | 90 |
| `test_unit_matching_distance.py` | 30 |
| `test_unit_store_e3_v6.py` | 13 |
| `test_unit_cli_backup_e3_v6.py` | 6 |
| `test_unit_service_v6.py` | 10 |

## 6. 바뀐 기존 테스트와 근거 Oracle 줄

테스트 작성자가 바꿨다. 통합 담당은 두 가지를 직접 확인했다. 근거 줄이 매니페스트 v.6에 있다는 것, 그리고 아래 "기준선" 열의 결과(§4 (b))다.

| 테스트 | 바뀐 것 | 근거 Oracle 줄 | 기준선 |
|---|---|---|---|
| `test_oracle_matching.py::test_must_m1_domain_distance` | `matching.domain_distance`(A2 0, B 1, D 1)를 단언하던 것을, `MatchCandidate.distance`가 독립 기준 구현 `_v6.reference_distance`와 같은지 보도록 바꿨다(A2 0, B ≈ 0.75, D < 1) | MUST-M5 "신고한 분야(`domains`)와 제목은 거리에 쓰지 않는다". §9 (v.6) "B·C(거리 약 0.75·0.81)" | 빨강 |
| `test_oracle_matching.py::test_prov_m2_diversity_includes_a_distant_relevant_candidate` | 끼워 넣은 멤버의 거리 조건: `== 1.0` → `>= far_distance` | MUST-M2 "거리가 `far_distance`(config) 이상인 자격 후보". §9 (v.6) "정확히 1.0이 드물어 다양성 보장의 '먼 후보' 기준을 0.5로 둔다" | 초록. 조건을 완화한 것이다. 예전 단언은 새 구현에서 빨강이다(Builder M 보고) |
| `test_oracle_matching.py::test_prov_m2_canal_open_default_strategy_includes_distant_member` | 멤버 중 하나의 거리 조건: `== 1.0` → `>= far_distance` | 같은 줄 | 초록 (완화) |
| `test_oracle_v4_matching.py::test_must_m1_v4_diversity_swap_never_brings_in_a_below_tau_candidate` | 자체 점검 "약한 후보는 거리 1.0(분야)"을 기준 구현의 내용 거리(0.78~1.0, 모두 far_distance 이상, W_TWO는 정확히 1.0)로 바꿨다. "τ 미만은 뽑히지 않는다"는 단언은 그대로다 | MUST-M5. MUST-M2 "가산점 때문에 τ 미만 후보가 선택됨"(금지) | 빨강 |
| `test_oracle_tiers.py::test_must_t1_members_truncated_by_relevance_and_flagged` | 주석만 바꿨다(F ≈ 0.60, B ≈ 0.63, C ≈ 0.64). 단언은 그대로이고, 잘리는 후보는 여전히 A2(0.56)다 | MUST-M2, MUST-M5, MUST-T1 "선택 전략의 순위(기본: MUST-M2 점수, v.5) 순으로 잘라내고" | 초록 |
| `test_oracle_v5_matching.py` 모듈 docstring, 손으로 만든 문서 5개, `_ref_distance` | `_ref_distance`를 분야 Jaccard에서 내용 거리 기준 구현으로 바꿨다. "가까운" 문서는 내용 거리 0이 되도록 다시 만들었다. 그 문서들은 호스트에 없는 분야를 신고한다. v.5 기준이었다면 먼 문서다 | MUST-M5 | — |
| `…::test_must_m2_v5_constructed_candidates_have_the_intended_values` | 기대 거리를 내용 거리 범위로 바꿨다. QT/T_FAR가 정확히 비기는지 자체 점검을 더했다 | MUST-M5 | 초록 (자체 점검) |
| `…::test_must_m2_v5_score_field_on_q01_matches_the_formula` | B 0.70 → 0.6260, C 0.70 → 0.6439. 비교 허용 오차는 표시 반올림 범위(1e-3)다 | §9 (v.6) "B·C(거리 약 0.75·0.81)". MUST-M2 "반올림은 응답에 보일 때만" | 빨강 |
| `…::test_must_m2_v5_q01_ranks_b_and_c_above_a2` | max_members = 1에서 뽑히는 후보: B(id 동점 처리) → C(내용상 더 멂) | MUST-M2 "관련도가 같으면 먼 분야가 위다", "Q-01은 B·C가 A2보다 위" | 빨강 |
| `…::test_must_m2_v5_full_tie_is_broken_by_subbrain_id_ascending` | B·C가 더 이상 비기지 않는다. 그래서 완전 동점은 C와 내용이 같은 사본(`sb_0C`)으로 만든다 | MUST-M2 "(같으면 관련도, 그다음 subbrain_id 오름차순)" | 빨강 |
| `…::test_must_m2_v5_equal_relevance_farther_field_ranks_higher` | 가까움·중간·멂을 내용 거리로 정했다(0 / ≈ 0.21 / B ≈ 0.75). 중간 후보의 점수는 2/3 대신 기준 구현 거리로 계산한다 | MUST-M2 "관련도가 같으면 먼 분야가 위다", MUST-M5 | 빨강 |
| `…::test_must_m2_v5_equal_score_is_broken_by_relevance_before_subbrain_id` | QK 질의로는 관련도 > 0이면서 내용 거리 1.0인 후보를 만들 수 없다. 그래서 QT와 T_FAR(거리 정확히 1.0) 대 CLOSE_050(0.0)으로 바꿨다 | MUST-M2 "(같으면 관련도, 그다음 subbrain_id)" | 빨강 |
| `…::test_must_m2_v5_below_tau_distant_candidate_never_selected_even_if_its_score_would_win[1,3,10]` | "점수였다면" 자체 점검을 1.0 대신 기준 구현 거리로 계산한다 | MUST-M2 금지 결과 "가산점 때문에 τ 미만 후보가 선택됨" | 빨강 ×3 |
| `…::test_must_m2_v5_diversity_guarantee_still_applies` | 먼 후보를 거리 ≥ far_distance로 정했다. T(AT_TAU_DOC)는 ≈ 0.56이다 | MUST-M2 v.6 다양성 보장 | 빨강 |
| `…::test_must_m2_v5_q02_keeps_a2_first` | B·C 점수를 표시 허용 오차로 비교한다. `_ref`가 내용 거리를 쓴다 | §9 (v.5) "주제 없는 질의(Q-02)에서는 A2(1.00)가 여전히 위다" | 빨강 |
| `…::test_must_m2_v5_distance_bonus_is_read_from_config` | 가산점 0.1에서 뽑히는 집합: {A2, B} → {A2, C} | MUST-M2 "`distance_bonus`(config)", MUST-M5 | 빨강 |
| `…::test_must_m2_v5_match_explain_exposes_score` | B 점수 0.70 → 0.6260 (표시 허용 오차) | §9 (v.6), MUST-M2 "응답에 후보별 `score`가 있다" | 빨강 |

## 7. 사보타주

### 7.1 통합 변경 (통합 담당이 직접 실행)

변이마다 작업 트리 src를 새로 복사하고 변경 하나만 되돌렸다. 그다음 `tests/unit/test_unit_service_v6.py`(10개)를 돌렸다. 변이 없는 사본은 10 passed다.

| 변이 | 되돌린 것 | 결과 | 잡은 테스트 |
|---|---|---|---|
| S1 | `service.py` 전체를 `c817d43` 판으로 | **빨강** 4 | τ 1/3 유지, search 표시 반올림, 멤버 순서, match_explain ranking |
| S2 | canal_open에 반올림된 `c.relevance >= τ` 재검사만 되살림 | **빨강** 1 | `test_canal_open_keeps_a_member_selected_at_exactly_tau_boundary_one_third` |
| S3 | canal_open 멤버 순서만 `in_rank_order`(반올림)로 | **빨강** 1 | `test_canal_open_members_follow_the_exact_ranking_when_scores_round_alike` |
| S4 | search 응답에 반올림하지 않은 관련도 | **빨강** 1 | `test_subbrain_search_rounds_relevance_only_for_display` |
| S5 | CLI가 `ranking`을 무시 | **빨강** 2 | `…_cli_table_follows_it`, `test_cli_rank_order_falls_back_when_the_ranking_does_not_fit` |

`test_canal_open_leaves_out_a_candidate_that_only_displays_at_tau`는 어떤 변이에서도 초록이다. 이 테스트는 회귀 방지용이다. τ 판정은 `match()`가 하므로 service 변이로는 깨지지 않는다.

### 7.2 빌더 사보타주 (보고된 대로, 다시 돌리지 않음)

- **Builder M**: `matching.py`를 9가지로 깨뜨렸고, 모두 단위 테스트에 잡혔다. 깨뜨린 방식은 config를 이진 float로 읽기, 순수 float 연산, 순위 전 반올림, τ 비교 반올림, far를 `== 1.0`으로, 텍스트를 합친 뒤 토큰화, 불용어 미제거, 후보마다 호스트 벡터 재생성, 분야를 내용으로 포함이다. PYTHONHASHSEED 세 가지에서 출력이 바이트 단위로 같았다.
- **Builder E3**: 기준선 `store.py`에 대해 새 단위 테스트가 0o644(420)로 빨강임을 확인했다. 테스트는 umask 022와 000에서 돌렸다.
- **테스트 작성자**: 스파이 대조 테스트를 두 개 두었다. 하나는 같은 프로세스 안에서 세 경우를 본다. 짧게 살았다 사라지는 0644 사본은 잡고, mkstemp 0600 사본은 통과시키고, 0644로 쓴 뒤 chmod로 좁힌 사본은 잡는다. 다른 하나는 sitecustomize로 주입한 하위 프로세스에서 0644 사본을 잡는다. 두 테스트 모두 기준선과 지금 실행(736 passed)에서 통과한다.

통합 담당은 이 결과들을 다시 돌리지 않았다. 대신 §4 (b)·(c1)·(c2)에서 v.6 이전 src가 새 oracle 테스트에서 빨강이라는 것을 직접 봤다.

## 8. 스모크

`zsh $I/smoke.sh $I`. `umask 022`인 새 scratch 디렉터리에서 실제 콘솔 스크립트(`.venv/bin/opencanal`)를 돌렸다. 순서는 `init-db` → `seed-fixtures`(fixture 7개, 사용자 6명) → `set-tier user_a pro` → `match-explain` → `backup` → `restore`다. 출력은 `$I/smoke_out.txt`에 있다. 토큰은 출력과 이 문서에 적지 않았다.

스모크는 두 번 돌렸다. 두 번째는 CLI 머리의 `tau`를 넷째 자리로 바꾼 뒤였다. 아래 값은 두 번째 실행의 것이고, 첫 번째 실행과 숫자는 모두 같다. 단 D와 X는 관련도와 점수가 모두 0이라 순서가 무작위 subbrain_id로 정해진다. 그래서 4·5위는 실행마다 바뀔 수 있다(첫 실행에서는 D가 4위였다).

### 8.1 `match-explain` (user_a, Pro, 호스트 A, max_members 6)

Q-01 "모듈러 건축의 현장 조립 오류를 줄일 아이디어". `query_mode_used: topic`, `strategy: relevance_with_distance_bonus`, `tau: 0.2000`, `query_terms: 모듈러, 건축, 현장, 조립, 오류`, `truncated: False`.

| rank | fixture | 제목 | relevance | distance | score | matched_terms | selected | reason |
|---|---|---|---|---|---|---|---|---|
| 1 | C | 단백질 자기조립과 오류 교정 | 0.4000 | 0.8131 | 0.6439 | 조립, 오류 | yes | selected_score |
| 2 | B | 퍼즐 게임 블록 설계 원칙 | 0.4000 | 0.7532 | 0.6260 | 조립, 오류 | yes | selected_score |
| 3 | A2 | 목조 모듈러 주택 설계 메모 | 0.5600 | 0.0000 | 0.5600 | 모듈러, 건축, 현장 | yes | selected_score |
| 4 | X | 사내 보안 점검 체크리스트 | 0.0000 | 1.0000 | 0.0000 | | no | below_tau |
| 5 | D | 동네 빵집 단골 만들기 | 0.0000 | 0.9755 | 0.0000 | | no | below_tau |

- **B와 C.** 관련도가 0.40으로 같고, 내용상 더 먼 C가 위다. v.5에서는 둘 다 0.70이었고, 순서는 무작위 id가 정했다.
- **MUST-M2 "Q-01은 B·C가 A2보다 위".** 성립한다.
- **D.** 거리가 1이 아니라 0.9755다. A의 라벨·요약과 우연히 겹치는 낱말이 있기 때문이다. 관련도가 0이므로 뽑히지 않는다(NEVER-08). §6.1의 "Q-01·Q-02 용어와 호스트 A 태그를 하나도 공유하지 않는다"와 어긋나지 않는다. 이 문장은 태그와 질의 용어에 대한 제약이고, 겹친 낱말은 그 밖에 있다.

Q-02 "내 두뇌를 평가해줘". `query_mode_used: whole_host`(호스트 태그·라벨 용어 36개), `truncated: False`.

| rank | fixture | relevance | distance | score | matched_terms | selected | reason |
|---|---|---|---|---|---|---|---|
| 1 | A2 | 1.0000 | 0.0000 | 1.0000 | 모듈러, 건축, 현장, 품질, 상세, 시공, 치수, bim, 공장, 모듈, 관리, 유닛 | yes | selected_score |
| 2 | C | 0.4500 | 0.8131 | 0.6939 | 조립, 오류, 유닛 | yes | selected_score |
| 3 | B | 0.4000 | 0.7532 | 0.6260 | 조립, 오류 | yes | selected_score |
| 4 | X | 0.0000 | 1.0000 | 0.0000 | | no | below_tau |
| 5 | D | 0.0000 | 0.9755 | 0.0000 | | no | below_tau |

§9 (v.5) "주제 없는 질의(Q-02)에서는 A2(1.00)가 여전히 위다"와 맞는다. MUST-M3에 따라 D는 빠진다.

### 8.2 백업·복원 (TMPDIR = 빈 scratch 디렉터리)

| 확인 | 결과 |
|---|---|
| `backup` 동안 TMPDIR·데이터 디렉터리·출력 디렉터리 감시. 0.5ms 간격으로 696번 훑으며 파일과 권한, SQLite 헤더 여부를 기록했다 | 본 파일은 셋이다. 살아 있는 DB(0600, SQLite), 그 `-wal`·`-shm`(0600), 마스터 키(0600). 새로 생긴 파일은 `.db.enc`(0600) 하나뿐이다. **TMPDIR에는 아무 파일도 생기지 않았다** |
| 백업 뒤 TMPDIR, 데이터 디렉터리 | TMPDIR은 비어 있다. 데이터 디렉터리의 파일 목록은 백업 전과 같다 |
| `.db.enc` | 0600, 출력 디렉터리 0700. 169,400바이트. 안에 `SQLite format 3` 매직이 없고, fixture 문구 "형태 상보성"(UTF-8)도 없다 |
| 같은 감시로 `c817d43` src(`git archive`) 백업 | TMPDIR에 `opencanal-snap-*/snapshot.db`(**0o644**, SQLite)와 `snapshot.db-journal`(**0o644**)이 보였다. 끝난 뒤에는 지워져 있었다. 스모크 감시 방식으로도 예전 동작을 잡을 수 있다는 뜻이다 |
| `restore` 동안 TMPDIR·대상 디렉터리 감시 (738번) | 대상 옆에 `..opencanal.db.restore-*.tmp.*.restoring`(0600, SQLite)이 잠깐 생겼다. 그다음 `opencanal.db`(0600)가 생겼다. **TMPDIR은 비어 있었다** |
| 복원 뒤 | 대상 디렉터리에는 `opencanal.db`(0600) 하나만 남았다. `-wal`·`-shm`·`-journal`은 없다 |
| 복원본 헤더·무결성 | 헤더 바이트 18/19 = 1/1(롤백 저널), `PRAGMA journal_mode` = `delete`, `quick_check` = `ok`. 원본과 테이블 10개의 행 수가 모두 같다. `subbrain_versions`는 7행이다 |
| 복원본으로 `match-explain` Q-01 | §8.1의 Q-01 표와 같다(순서, 관련도, 거리, 점수) |

복원 대상 디렉터리는 스크립트가 미리 만들었으므로 0755다. CLI가 새로 만드는 디렉터리라면 0700이다(CHANGE-004 §8.1).

### 8.3 독립 계산 대조

통합 담당이 `_v6.py`와 `matching.py`를 쓰지 않는 스크립트를 따로 짰다(15줄). 낱말은 `textnorm.tokenize`로 뽑았다. 라벨·태그·요약 하나하나를 텍스트 하나로 보고, 텍스트마다 토큰화한 뒤 개수를 더했다. 결과:
- 호스트 A 대비 코사인과 거리: A2 0.3401 / 0.0000, B 0.0617 / 0.7532, C 0.0467 / 0.8131, D 0.0061 / 0.9755, X 0 / 1.0
- Q-01 점수: B 0.625970, C 0.643940
- Q-02 점수: C 0.693940

모두 §8.1 표와 같고, §9 (v.6)의 "A–A2 코사인 0.34", "B·C 거리 약 0.75·0.81"과도 맞는다.

## 9. 해석 — 오너 확인이 필요한 것

테스트 작성자와 빌더가 같은 해석을 택했고, 통합 담당도 Oracle 문장과 모순되지 않음을 확인했다. 다만 Oracle이 직접 정하지 않은 부분이다.

1. **낱말 빈도의 단위.** 라벨·태그·요약 하나하나를 텍스트 하나로 본다. 텍스트마다 토큰화하고(한 텍스트 안의 중복은 하나로 센다) 개수를 더한다. 이 읽기만 §9의 0.34 / 0.75 / 0.81을 재현한다. 노드 단위로 읽으면 0.37 / 0.74 / 0.84이고, 문서 전체로 읽으면 더 벗어난다. MUST-M5 문장의 "낱말 빈도 벡터"는 단위를 말하지 않는다.
2. **`relevance_plus_diversity`의 먼 후보.** 이 전략에서도 다양성 교체 조건이 `distance >= far_distance`다. MUST-M2 v.6 문장은 기본 전략을 설명하는 자리에 있다. 근거는 §9 (v.6) "정확히 1.0이 드물어 다양성 보장의 '먼 후보' 기준을 0.5로 둔다"이다. 오너가 거부할 수 있다. 그 경우 `test_prov_m2_diversity_includes_a_distant_relevant_candidate`와 `matching._guarantee_diversity`를 함께 바꿔야 한다.
3. **복원 대상도 늘 0600.** 테스트는 복원되는 DB 자체도 관찰하는 모든 순간 0600이어야 한다고 본다. 0644로 쓴 뒤 chmod로 좁히면 실패한다. 근거는 v.6 임시 파일 조항이 아니라 v.5 MUST-E3 "opencanal이 만들거나 여는 DB 파일 … 0600"이다.
4. **"호스트는 커널에 쓰는 버전".** 멤버 거리는 커널이 기록한 `host_version` 기준이다. 그 버전이 어느 것인지는 테스트가 고정하지 않는다. 지금 구현의 `_host_version`은 이렇게 고른다.
   - canal_open: 공개된 버전(`published_version`)을 쓴다.
   - match_explain: 호스트가 공개 상태면 공개 버전을, 아니면 최신 버전을 쓴다.
5. **노드 type, 엣지 요약.** 이 둘은 거리에 쓰지 않는다. MUST-M5가 "노드 라벨·태그·요약"만 적었기 때문이다(`test_must_m5_other_fields_do_not_count`).
6. **`test_oracle_tiers.py`의 낡은 주석.** 주석의 "MUST-T1's '상위 관련도 순' predates v.5"는 현재 매니페스트의 MUST-T1("선택 전략의 순위(기본: MUST-M2 점수, v.5) 순으로")과 맞지 않는다. 단언에는 영향이 없다. 테스트 작성자가 정리할 일이다.

## 10. 남은 위험

| 위험 | 내용 | 정도 |
|---|---|---|
| 거리 계산 비용 | `match()`가 부를 때마다 모든 후보의 낱말 벡터를 새로 만든다(캐시 없음). Builder M 보고로는 노드 2000개짜리 후보 20개에 약 2초가 걸리고, 대부분이 토큰화 시간이다. canal_open과 match_explain마다 공개 서브브레인 수에 비례해 늘어난다 | 중간 (R0 규모에서는 괜찮다) |
| 수학적으로 같은 거리의 float 차이 | 거리에는 `sqrt`가 들어가므로 float다. 수학적으로 같은 두 거리가 1 ulp 다를 수 있다(확인한 예: 1/√17과 3/√153 → 0.029857499854668124 대 …013). 그러면 MUST-M2의 동점 규칙("같으면 관련도, 그다음 subbrain_id")이 적용되지 않고 float 잡음이 순서를 정한다. 결과는 여전히 결정적이다. 이런 일은 낱말 빈도가 정확히 비례하는 두 후보에서만 생긴다 | 낮음 |
| serialize 대체 경로 | `_backup_via_private_file`(0700 디렉터리의 0600 파일)은 `_CAN_SERIALIZE`를 monkeypatch해야만 시험된다. 이 환경의 SQLite 3.53.1은 serialize를 지원한다 | 낮음 |
| 헤더 직접 수정 | 백업 이미지의 바이트 18/19를 코드가 직접 고친다. SQLite 파일 형식 문서에 정해진 자리다. 스모크와 빌더 테스트에서 `quick_check`, `journal_mode`, `deserialize`, `immutable=1` 열기를 모두 확인했다 | 낮음 |
| 복원 중 강제 종료 | SIGKILL을 받으면 대상 옆에 0600 평문 임시 파일(`..<name>.restore-*.tmp.*.restoring`)이 남을 수 있다. macOS에서 이식성 있게 막을 방법이 없다(Builder E3 보고) | 낮음 (0600, 같은 디렉터리) |
| 백업 쓰기 실패 | 디스크가 차는 등으로 백업 쓰기가 중간에 실패하면 부분 `.db.enc`가 남는다. 암호문이고 0600이다 | 낮음 |
| CLI 대체 순서 | `ranking`이 없는 envelope(예전 서버, 다른 전송)에서는 CLI가 반올림한 필드로 정렬한다. 점수가 같은 값으로 반올림되면 순위 열이 실제 선택과 어긋날 수 있다 | 낮음 |
| 기준선 판별력 | §4의 흔들린 테스트 1건은 v.5에서 약 절반 확률로 통과한다. 다른 테스트가 같은 사실을 결정적으로 잡는다 | 낮음 |
| 오너 확인 대기 | §9 (v.6)의 `distance_saturation` 0.25와 `far_distance` 0.5는 플래너 제안이다. §9의 해석 1·2도 오너 확인 전이다. 오너가 바꾸면 기준과 테스트를 먼저 고친다(§8) | — |

## 11. 적대 확인 — 내용 거리의 float 오차가 MUST-M2 동점 규칙을 뒤집음

> 2026-10-06, 빌더-통합 담당(float 동점)이 남긴 기록이다. 기준 문서는 MUST-M2 (v.6) "점수 순 (같으면 관련도, 그다음 subbrain_id 오름차순) … 반올림하지 않은 값으로", MUST-M5 "거리 = 1 − min(1, 유사도 ÷ `distance_saturation`)", §9 (v.6) "반올림 전 값으로 비교" 행이다. 커밋하지 않았다. `$V`는 이 세션 scratchpad의 `v6/`, `$B`는 `$V/floattie-builder/`다.

**원인 하나.** `_distance_between`이 코사인을 `dot / math.sqrt(norms)`(이진 float)로 계산했다. 그 오차가 `score = relevance + bonus * Fraction(distance)`를 거쳐 "정확한" 분수 점수에 들어갔다. 그래서 수학적으로 같은 점수가 마지막 비트에서 갈렸고, `_score_key`의 관련도·subbrain_id 동점 규칙은 실행되지 않았다. 모듈 docstring(옛 12–16행)의 "수학적으로 같은 값은 같게 비교되고 동점 규칙이 지켜진다"는 거리에서는 거짓이었다. §10의 "수학적으로 같은 거리의 float 차이" 행(정도 낮음)이 바로 이 결함이다.

### 11.1 수정

| 파일 | 변경 |
|---|---|
| `src/opencanal/matching.py` `_distance_between` | 약분된 분수 cos² = dot² / (\|H\|²·\|C\|²)에서 시작한다. 포화 판정은 cos² ≥ saturation²로 정확히 한다. cos²의 분자·분모가 모두 완전제곱(`math.isqrt`)이면 코사인이 유리수이고, 거리를 정확한 `Fraction`으로 돌려준다. 아니면 (cos / saturation)² 분수 하나에서 float를 만든다. 그래서 cos²가 같으면 float도 비트 단위로 같다. config 숫자는 적힌 십진수(`_exact`)로 읽는다 |
| 같은 파일 `content_distance` | 공개 반환값은 그대로 float이다. 정확한 값에 가장 가까운 float를 준다(1/3 → 0.3333333333333333, 예전 0.33333333333333337) |
| 같은 파일 `_guarantee_diversity` | `far_distance`를 `_exact`로 읽어 정확히 비교한다. 거리가 정확히 far_distance면 먼 후보다 |
| 같은 파일 `_Scored.distance`, 모듈 docstring | 타입을 `Fraction \| float`로 바꿨다. docstring에 정확성 계약과 그 근거를 적었다 |
| `tests/unit/test_unit_matching_exact_ties_v6.py` (신규, 15개) | 아래 재현 전부, far_distance 경계 2건(전략 2개씩), 정확한 기준 구현(a + b·√u 꼴을 부호로 비교, float 없음)과 대조하는 퍼즈 4건(설정 4가지 × 300회, 동점 자체 점검 포함) |

**이것으로 충분한 이유.** 두 점수 r1 + b(1 − c1/s)와 r2 + b(1 − c2/s)가 정확히 같으려면 c1 − c2가 유리수여야 한다. c = √q(q는 유리수)일 때 그런 경우는 둘뿐이다. q1 = q2이면 이제 같은 float가 나온다. 아니면 두 코사인이 모두 유리수이고, 이제 정확한 분수다. 포화된 후보(c = s)와 공통 낱말이 없는 후보(c = 0)는 유리수 쪽이다. 따라서 수학적 동점은 모두 MUST-M2의 동점 규칙으로 정해진다.

고정 파일(`docs/`, `config/`, `fixtures/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)과 `tests/oracle`은 건드리지 않았다. 시작과 끝의 해시를 비교했을 때(`$B/hashes_start.txt`, `$B/hashes_end.txt`) 달라진 것은 `matching.py`와 새 단위 테스트 파일뿐이다.

### 11.2 재현 (수정 전 = 기준 `matching.py` 사본 `$B/matching_before.py`, 수정 후 = 작업 트리)

| id | 재현 | 수정 전 | 수정 후 |
|---|---|---|---|
| M2-FLOAT-TIE-1 (서로 다른 후보, 유리 코사인) | `$V/m5-judge/exp2b_tie_relevance.py`. P: 관련도 1/5, cos 7/40 → 거리 3/10, 점수 29/100. Q: 관련도 29/100, 거리 0, 점수 29/100. max_members 1 | P 거리 0.30000000000000004. **P(0.2) 선택**, Q(0.29) `truncated_by_limit`. 표시 점수는 둘 다 0.29. AssertionError | **Q 선택**, P `truncated_by_limit`. 종료 코드 0. 내부 거리는 정확히 3/10 |
| M2-FLOAT-TIE-1 (배수 벡터) | `$V/m5-judge/exp2_tie.py`. sb_b의 낱말 벡터는 sb_a의 정확히 3배다. cos² 1/18, 관련도 4/5 | 거리 0.05719095841793653 대 0.057190958417936644. **sb_b 선택**. AssertionError | 두 거리가 0.057190958417936644로 같다. **sb_a 선택**. 종료 코드 0 |
| M2-V6-FLOATTIE-1 (최소 사례) | `$V/m2-ranking-judge/exp5_min_tie.py`. X: 관련도 1, 거리 0, 점수 1. Y: 관련도 9/10, cos 1/6, 거리 1/3, 점수 1 | Y 거리 0.33333333333333337. **Y 선택**, X `truncated_by_limit`. "DEFECT" | **X 선택**, Y `truncated_by_limit`. "ok". 공개 `content_distance`는 0.3333333333333333(1/3에 가장 가까운 float)이므로 스크립트의 "exact 1/3? False"는 float 표시 때문이고, 내부 값은 `Fraction(1, 3)`이다 |
| M2-V6-FLOATTIE-1 (서비스 경로) | `$V/m2-ranking-judge/exp2_relevance_tiebreak.py`. Free `canal_open`(3자리), Pro `match_explain`. X: 1 + 0.3·0 = 1. Y: 0.8 + 0.3·2/3 = 1 | canal_open 멤버 [G1, G2, **Y**], X 빠짐. match_explain에서 Y(0.8)가 X(1.0)보다 위다 | canal_open 멤버 [G2, G1, **X**]. match_explain에서 X가 Y보다 위다. G1·G2는 서로 완전 동점이라 무작위 id 순서를 따른다. "ok" |
| M2-V6-FLOATTIE-1 (퍼즈) | `$V/m2-ranking-judge/exp4_fuzz.py <seed> 4000`, seed 1·2·3. 60자리 Decimal 기준과 대조 | 불일치 5 / 6 / 4 = **15건**. 모두 정확한 점수 동점에서 났다(`$B/before_runs/`에서 기준 사본으로 직접 실행) | **0 / 0 / 0** |
| M2-V6-FLOATTIE-2 (fixture C ×7) | `$V/m2-ranking-judge/exp1_float_tie.py`. 호스트 A, Q-01, C와 C를 7번 반복한 사본. 둘 다 cos² 289/132418, 관련도 2/5 | 0.8131318007134303(C) 대 0.8131318007134304(7×C). **sb_ZZZ 선택**, sb_AAA `truncated_by_limit`. "DEFECT" | 스크립트가 "no case"로 끝난다(종료 코드 1). 수학적으로 같은 거리인데 float가 다른 쌍이 이제 없어서이고, 의도된 결과다. 같은 사례를 단위 테스트 `test_fixture_c_repeated_ties_by_subbrain_id[7, 13]`에 고정했다. **sb_AAA 선택** |
| M2-V6-FLOATTIE-2 (중복 없는 내용) | `$V/floattie2-refuter/r1_natural.py`. 낱말이 모두 다르고 노드·라벨 반복이 없는 쌍이다. d1²·n2 = d2²·n1 | float가 다른 쌍 **23개**. ('현장', m 2, k 5)에서 입력 순서와 관계없이 **sb_ZZZ 선택** | **0개**. 두 입력 순서 모두 **sb_AAA 선택** |
| 추가 (같은 원인, 수정 중 발견) | far_distance 경계. config를 `model_copy`로 saturation 0.2, far_distance 0.3으로 바꾼다. F의 cos = 7/50(\|H\|² 10, \|F\|² 250, dot 7)이므로 거리는 정확히 3/10이다 | 거리 0.29999999999999993 < 0.3. 먼 후보로 보지 않아 다양성 보장이 F를 넣지 않았다. MUST-M2 "거리가 `far_distance` 이상" 위반이다. 기본 config(0.25, 0.5)에서는 경계가 이진수로 정확히 표현돼 일어나지 않는다 | 거리 `Fraction(3, 10)`. F `selected_diversity`, N `displaced_by_diversity`(두 전략 모두) |

위 재현 스크립트 일곱 개는 모두 작업 트리 `src`를 import한다(스크립트의 `sys.path`와 `matching.__file__` 확인). 반박자 점검 `$V/m2-float-tie-refuter/verify.py`와 `$V/m2-floattie-refuter/refute1.py`도 다시 돌렸다. 둘 다 이제 Oracle의 승자(sb_Q, sb_a, sb_a_X)와 구현의 승자가 같다고 출력한다.

### 11.3 사보타주

`$B/mutA_*`는 작업 트리 src 사본에 변경 하나만 넣은 것이다. 실행은 `OPENCANAL_CONFIG_DIR=<repo>/config .venv/bin/python -m pytest -q -o pythonpath=$B/mutA_sN/src tests/unit/test_unit_matching_exact_ties_v6.py`. 변이 없는 작업 트리는 15 passed다.

| 변이 | 바꾼 것 | 결과 |
|---|---|---|
| s0 | 수정 전 `matching.py` 전체 | **빨강 14** / 15 (seed 4 퍼즈만 초록) |
| s1 | 유리 코사인의 정확한 분수 경로를 끔(항상 float) | **빨강 8**: 1/6·7/40 동점, 정확한 거리, far 경계 4, 퍼즈 seed 1 |
| s2 | 무리 코사인 float를 예전처럼 `dot / sqrt(norms)`로 | **빨강 7**: 배수 벡터, C×7·×13, 중복 없는 쌍, 퍼즈 3 |
| s3 | far_distance를 이진 float 그대로 비교 | **빨강 2**: `test_far_distance_is_compared_as_the_decimal_it_is_written_as`(전략 2). 0.4의 float는 2/5보다 조금 크다 |
| s4 | 포화 판정을 float(`cos / s >= 1`)로 | 초록 15 (**살아남음**). 유리 코사인이 포화값과 정확히 같으면 두 float도 같아서 판정이 같다. 다르게 판정하려면 \|H\|²·\|C\|²가 약 10³²을 넘어야 해서 단위 테스트로 만들 수 없다. 사실상 동치 변이로 본다 |

### 11.4 전체 결과와 스모크

- `umask 022; .venv/bin/python -m pytest -q -p no:cacheprovider`: **1611 passed** (12.9s). oracle 736, unit 875. 수정 전 작업 트리는 1596 passed였고, 늘어난 15개는 새 단위 테스트다. 기존 테스트는 하나도 바꾸지 않았다.
- 비용: 후보 1800개에서 `_distance_between`은 후보당 5.7µs → 7.5µs, `match()`는 927ms → 951ms다. 시간 대부분은 토큰화다(`$B/perf.py`).
- 스모크 `zsh $B/smoke_explain.sh $B/smoke1`(실제 콘솔 스크립트, 토큰은 출력하지 않음): `match-explain` Q-01·Q-02 표가 §8.1과 숫자·순서 모두 같다. 0점인 D·X의 순서만 무작위 id를 따른다. 출력은 `$B/smoke_out.txt`에 있다.

### 11.5 tests/oracle에 더할 테스트 (플래너 몫, 빌더는 쓰지 않았다)

`_v6.reference_distance`, `reference_score`, `m2_order_key`는 float 기준이다. 그래서 정확한 동점에서는 기준 구현 자체가 float 오차로 순서를 정한다. 동점 테스트에는 손으로 구한 정확한 값을 쓰거나, cos²를 `Fraction`으로 다루는 기준이 필요하다.

1. `test_must_m2_v6_exact_score_tie_is_broken_by_relevance`: 호스트 낱말 {s, h1, h2, h3}. X = 같은 낱말 + 태그 kw, ab(관련도 1, 거리 0, 점수 1). Y = 태그 kw, 라벨 "ab s f1..f6"(관련도 9/10, cos 1/6, 거리 1/3, 점수 1). 질의 "kw ab", max_members 1. id는 subbrain_id 규칙이 Y 편이 되게 고른다. 기대: X가 위에 오고 선택된다. 같은 모양을 `canal_open`(Free)과 `match_explain`으로도 확인한다(exp2_relevance_tiebreak 모양: X 거리 0, Y cos 1/12 → 거리 2/3).
2. `test_must_m2_v6_equal_cosine_full_tie_is_broken_by_subbrain_id`: fixture C와 C를 7번 반복한 사본(노드 id만 다름). 호스트 A, Q-01, max_members 1. 기대: 더 작은 subbrain_id가 선택된다. 두 입력 순서를 모두 본다. 자체 점검으로 정수 dot²·\|C\|²가 같은지 확인한다.
3. (선택) `test_must_m2_v6_distance_exactly_far_distance_is_far`: `model_copy`로 saturation 0.2, far_distance 0.3. cos 7/50 → 거리 정확히 3/10인 후보가 다양성 보장으로 들어와야 한다. MUST-M2 "거리가 `far_distance` 이상".

### 11.6 남은 위험

| 위험 | 내용 | 정도 |
|---|---|---|
| 동점이 아닌 근소한 차이 | 무리 코사인 두 개, 또는 유리 하나와 무리 하나의 실제 점수 차가 float 한 칸(약 1e-16)보다 작으면 순서가 반올림으로 정해질 수 있다. 정확한 동점은 위 논증으로 생기지 않는다. 그런 근소한 차이를 만들려면 큰 벡터가 필요하다고 보지만 하한을 증명하지는 않았다. 무리 거리와 far_distance의 비교도 같은 이유로 경계 바로 옆에서만 영향을 받는다 | 낮음 |
| 살아남은 변이 s4 | 포화 판정을 float로 해도 단위 테스트가 잡지 못한다. 실현 가능한 크기에서는 동치다 | 낮음 |
| 공개 값 변화 | `content_distance`가 유리 거리에서 정확한 값에 가장 가까운 float를 준다(예: 0.33333333333333337 → 0.3333333333333333). 표시값(넷째 자리)과 기존 테스트 1596개는 그대로다 | 없음 |
| §10 행 | "수학적으로 같은 거리의 float 차이"는 이 수정으로 해소됐다 | — |
