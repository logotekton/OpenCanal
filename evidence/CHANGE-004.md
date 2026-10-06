# CHANGE-004 — Oracle v.5 통합 기록 (먼 분야 가산점, 기여자 연결 불가, DB 0600)

> NDSH 부록 B-7 양식. 통합 담당(Integrator)이 2026-10-06에 남긴 기록이다. 사실만 적는다.
> 기준: `docs/oracle/ORACLE_MANIFEST.md` v2026-10-06.5 (§2 오너 결정, MUST-M2, NEVER-11, MUST-E3, §9 "(v.5)" 행, §10), `tasks/TASK-001.md`, 기준 커밋 `0699aa9`. 커밋하지 않았다.
> 작업 파일: `$V` = 이 세션 scratchpad의 `v5/`, `$I` = `$V/integrator/` (둘 다 저장소 밖). 기준선 worktree는 `$V/integ-base`에 만들었다가 지웠다.

## 1. 오너 결정 4건과 반영

| # | 오너 결정 (§2) | Oracle 기준 | 구현 반영 | 고정한 테스트 |
|---|---|---|---|---|
| 1 | 같은 분야 이웃이 먼 분야 다리보다 위에 오는 매칭 → **먼 분야에 가산점** | MUST-M2 (v.5, PROV-M2 대체). §9 `distance_bonus` = 0.3 | `matching.py`: 기본 전략 `relevance_with_distance_bonus`, `candidate_score`(자격 있는 후보만 관련도 + 0.3 × 거리, τ 미만은 0), 점수 → 관련도 → subbrain_id 순, 그 뒤 다양성 보장 (Builder M). 통합 단계: `MatchResult.candidates`는 관련도 순으로 유지하고, 순위는 `in_rank_order`로 얻는다. canal_open `members[]`는 점수 순이다. match-explain 표에 순위·점수 열을 넣었다. 관련도 필드는 노드 태그·라벨·요약으로 한정했다 (§2.1) | `test_oracle_v5_matching.py` 48개 (함수 22개) |
| 2 | "암호화"의 범위 → **여러 결과를 엮을 수도 없게** | NEVER-11 확대 (v.5). §9 `withheld_ref` | `crypto.contributor_token`: 324바이트 고정 프레임을 AES-SIV로 암호화한다. 토큰은 주인 ID 길이와 상관없이 늘 457자다. `crypto.withheld_ref`: HKDF 하위 키 `opencanal/withheld-ref/v1`로 `canal_id|subbrain_id`의 HMAC-SHA256을 구하고, 앞 16바이트에 `wr_`를 붙인다. canal_get의 비공개 항목은 `{withheld: true, withheld_ref}`만 담는다. 호스트가 비공개면 `canal.host_withheld_ref`를 준다. 델타브레인 뷰의 `host_subbrain_id`는 null이다. `create_user`는 64자를 넘는 ID를 거부한다 (Builder) | `test_oracle_v5_unlinkability.py` 19개 (함수 11개) |
| 3 | DB 파일 권한 → **지금 0600 적용** | MUST-E3 (v.5) | `crypto.make_private_dirs`(새로 만드는 디렉터리는 0700, 이미 있는 디렉터리는 그대로 둔다). `store._prepare_db_file`: 새 DB는 `O_EXCL` 0600으로 만들고, 기존 DB와 -wal/-shm/-journal은 0600으로 좁힌다. CLI의 DB·백업·복원 디렉터리에도 적용한다 (Builder) | `test_oracle_v5_file_modes.py` 9개 |
| 4 | 내용 없는 연결 자동 거르기 → **사람 평가 10개 뒤에** | §10 결정 기록. L1은 그대로 | 코드 변경 없음. `validator.py`는 `0699aa9`와 같다 (`git diff HEAD --stat -- src/opencanal/validator.py` 출력 없음) | 없음 (의도대로) |

2·3행의 내부 구현 값(324바이트 프레임, 457자, HKDF 라벨 `opencanal/withheld-ref/v1`, `O_EXCL`)은 **빌더 보고**에서 옮겼다. 통합 담당이 직접 확인한 것은 밖에서 보이는 동작이다. 그 근거는 셋이다: §4 (c)의 기준선 빨강 23건(NEVER-11 17, MUST-E3 6)이 지금은 모두 초록인 것, §8 스모크의 파일 권한, 그리고 1행의 매칭 결과다.

## 2. 변경 요약

병렬 단계에서 세 명이 작업했다. 테스트 작성자는 `tests/oracle`의 새 파일 3개와 수정 파일 5개를 맡았다. Builder M은 `matching.py`와 그 단위 테스트를, Builder는 `crypto.py`, `store.py`, `service.py`, `cli.py`와 그 단위 테스트를 맡았다. 시작할 때 작업 트리는 **4 failed, 1439 passed**였다. 통합 담당이 4건을 모두 src에서 고쳤다.

### 2.1 통합 단계에서 직접 바꾼 것

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/opencanal/matching.py` | `candidate_fields`가 노드의 태그·라벨·요약만 쓴다. 문서 제목, 도메인, 엣지 요약은 더 이상 관련도 필드가 아니다 | `test_must_m1_relevance_fields_are_node_tags_labels_and_summaries_only`와 `test_must_m2_v5_never_selects_below_tau[10-Q-02-None / -relevance_with_distance_bonus]`가 실패했다. W_LABEL의 도메인 '도시 계획'이 호스트 용어 '계획'과 맞아 관련도 0.36을 받았고, 기준값 0.16(τ 미만)인데도 뽑혔다. 기준 공식은 이미 고정돼 있었다: v.4부터 `tests/oracle`에 있던 `_v4.reference_relevance`, 스텁 docstring의 "fields (tags, label, summary)", config의 `field_weights` 키, D-003 "태그·라벨·요약의 어휘 겹침". Oracle 문장과 모순되지 않으므로 테스트가 아니라 src를 고쳤다. fixture와 golden 질의 결과는 바뀌지 않는다 (§8.3) |
| `src/opencanal/matching.py` | `select_relevance_with_distance_bonus`는 리스트를 제자리 재정렬하지 않는다. 점수 순으로 정렬한 사본에서 고르고 다양성을 보장한다. 이때 후보 객체는 바뀌지만 리스트 순서는 그대로다. `RANK_KEYS`와 `in_rank_order(candidates, strategy)`를 추가했고, `SelectionStrategy` 계약 문구를 고쳤다 | `test_must_m1_q01_selects_only_relevant_members_with_evidence`가 실패했다(`candidates are sorted by relevance desc`). 고정 파일 `models.py`는 `MatchResult.candidates`를 "sorted by relevance desc"라고 정한다. MUST-M2는 **무엇을 고를지**를 정할 뿐 목록 순서는 말하지 않는다. 테스트 작성자의 v5 모듈 docstring도 순위를 목록 순서로 보지 않는다고 밝힌다. 두 빌더는 이 건을 "오너 결정 필요"로 보고했지만 계약 안에서 풀린다. 그래서 `models.py` 주석이 낡았다는 빌더 보고는 이제 해당하지 않는다 |
| `src/opencanal/service.py` | canal_open의 `members[]`와 `untrusted_data.subbrains`를 `matching.in_rank_order(result.candidates, result.strategy)` 순서로 만든다. 저장되는 커널 멤버 순서도 같다 | 위 변경 뒤에도 `test_must_m2_v5_canal_open_q01_expert_host_lists_b_and_c_above_a2`를 지키기 위해서다. 잘리는 후보가 없으면 순위가 드러나는 곳은 members 순서뿐이다 |
| `src/opencanal/cli.py` | `match-explain` 표에 `rank`와 `score` 열을 넣었다. 행은 envelope의 `strategy`가 매기는 순위 순이다(`_in_rank_order`). 모양이 예상과 다르면 서버 순서를 그대로 쓴다 | 작업 지시 3번(새 점수 열과 순위)을 따랐다. 이전 표에는 점수 열이 없었다 |
| `tests/unit/test_unit_matching.py` (Builder M 파일) | 손으로 만든 후보 5개(A2, NEAR, A3, NEAR_HIGH, `close`)의 노드 태그에 도메인 낱말을 더해, 원래 의도한 관련도 값을 유지했다. A2는 whole_host 값 0.8을 지키려고 `bim`도 더했다. `test_score_counts_domains_title_and_edge_summaries`는 `test_score_ignores_domains_title_and_edge_summaries`로 바꿨다. 점수 순 단언은 `_ranked`(in_rank_order)로 옮겼다. 새 테스트 `test_candidates_are_listed_in_relevance_order_for_every_strategy[3종]`와 `test_in_rank_order_follows_the_strategy`를 넣었다 | 위 두 matching 변경에 맞췄다. 72 passed |
| `tests/unit/test_unit_mcp.py` | `test_match_explain_table_shows_score_and_ranks_by_the_strategy`를 추가했다 | CLI 표의 순위·점수 열과 전략별 행 순서를 고정한다 |
| `README.md` | init-db 줄에 "새로 만드는 데이터 디렉터리는 0700"을 더했다. match-explain 설명에 순위·점수 열과 행 순서를 더했다 | 사용자가 보는 설명을 실제 동작에 맞췄다 |
| `evidence/CHANGE-004.md` (신규) | 이 문서 | |

고정 파일(`docs/`, `config/`, `fixtures/`, `tests/oracle/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. `git diff HEAD -- docs config fixtures src/opencanal/models.py src/opencanal/textnorm.py src/opencanal/config.py pyproject.toml`의 출력은 비어 있다. `tests/oracle`의 변경은 모두 테스트 작성자가 했다. 통합을 시작할 때 수정·미추적 파일의 해시를 떠 두었다(`$I/hashes_start.txt`). 끝에 다시 비교하니 차이는 통합 담당이 고친 `cli.py`, `matching.py`, `service.py`, `test_unit_matching.py`뿐이었다. `test_unit_mcp.py`와 `README.md`는 시작할 때 수정되지 않은 상태였다. 그동안 다른 에이전트는 파일을 바꾸지 않았다. 스키마 변경은 없다(`store.py` diff에 `CREATE`·`ALTER`가 없다).

## 3. 실행 명령

```bash
# 자동 검사 (저장소 루트)
.venv/bin/python -m pytest -q -p no:cacheprovider

# 빨강 기준선 (저장소 밖 worktree. stash는 쓰지 않았다)
git worktree add $V/integ-base 0699aa9
cd $V/integ-base && export PYTHONPATH=$V/integ-base/src && umask 022
.venv/bin/python -m pytest -q -p no:cacheprovider --junitxml=$I/base_committed.xml           # (a) 커밋된 그대로
cp <tests/oracle 새 파일 3개 + 수정 파일 5개> tests/oracle/
.venv/bin/python -m pytest -q -p no:cacheprovider tests/oracle --junitxml=$I/base_neworacle.xml  # (b)
cp <작업 트리 matching.py> src/opencanal/ ; pytest tests/oracle ; 원복                         # (c) 분리 기준선
git worktree remove --force $V/integ-base && git worktree prune
# (d) git archive 0699aa9 사본 + 작업 트리 matching.py만: 커밋된 테스트 전체

# 사보타주: python $I/sabotage.py $I     스모크: zsh $I/smoke.sh $I
```

`PYTHONPATH`를 export한 이유가 있다. `_v4.cli_env`는 `os.environ`을 물려받는다. 그래서 `opencanal` 콘솔 스크립트 하위 프로세스도 worktree의 src를 import한다(PYTHONPATH가 editable `.pth`보다 앞선다). 확인은 두 가지로 했다. `PYTHONPATH=<worktree>/src .venv/bin/python -c "import opencanal; print(opencanal.__file__)"`가 worktree 경로를 찍었다. 그리고 CLI를 거치는 MUST-E3 테스트 2건(`..._cli_init_db_...`, `..._cli_restore_created_data_directory_is_0700`)이 기준선에서 빨강이었다.

## 4. 빨강 기준선

| 실행 | 결과 | 해석 |
|---|---|---|
| (a) `0699aa9` 그대로 (커밋된 테스트 1288개) | **67 failed, 25 errors, 1196 passed** | 원인은 하나다. config의 기본 전략 `relevance_with_distance_bonus`가 `STRATEGIES`에 없어서 `resolve_strategy`가 `ValueError: unknown matching strategy`를 낸다. 26건은 이 ValueError가 직접 보인다. 나머지 66건에서는 canal_open·match_explain이 같은 예외를 `INTERNAL` envelope로 바꿨고, 일부는 그 연쇄로 실패했다(`KeyError: 'canal_id'`, 월 한도 자체 점검, `assert False`). 로그에 같은 ValueError가 105번 찍혔다. 의도한 빨강이다 |
| (d) (a)에 작업 트리 `matching.py`만 넣음 | 7 failed, 1281 passed | 남은 7건은 모두 예전 기본값을 기대하는 테스트다. oracle 2건(`test_prov_m2_default_strategy_comes_from_config`, `test_must_t1_members_truncated_by_relevance_and_flagged`)과 HEAD 시점의 unit 5건이다. 그러므로 (a)의 92건은 모두 기본 전략이 없어서 생겼다 |
| (b) (a)에 새·수정 oracle 파일 8개 (tests/oracle 683개) | **100 failed, 42 errors, 541 passed** | v5 파일별: matching 44 failed / 4 passed, unlinkability 2 failed + 17 errors(setup의 canal_open이 INTERNAL), file_modes 6 failed / 3 passed. 테스트 작성자 보고(101 failed, 540 passed)와 1건 다르다. `test_must_e1_key_location_is_gitignored`가 실제 git worktree에서는 통과했다. 작성자가 짐작한 대로 그의 scratch REPO_ROOT 때문에 생긴 실패다 |
| (c) (b)에 작업 트리 `matching.py`만 더함 | **27 failed, 656 passed** | 매칭 실패에 가려졌던 v.5 빨강이 드러난다. **NEVER-11 17건**: v5_unlinkability 15건에 `test_never_02_private_switch_effects`와 `test_never_02_v4_host_switched_private_is_withheld_in_canal_get`을 더한 수다. 실제 subbrain_id가 보였고, withheld_ref가 없었고, 토큰 길이로 주인 ID 길이가 드러났다(1·6·20·40·64자 → 74·81·99·…자, 한 델타브레인 안에서 53자 대 137자). **MUST-E3 6건**: DB·-wal·-shm이 0644, 디렉터리가 0755였다. **MUST-M1/M2 4건**: 통합 단계에서 고친 4건(§2.1)이다 |

기준선에서 이미 통과한 v5 테스트는 원래 맞던 동작을 지키는 것들이다. file_modes 3건(`restore_bytes` 0600, 마스터 키 디렉터리 0700, CLI restore DB 0600)과 unlinkability 4건(델타브레인별 토큰 2건, 주인은 실제 ID를 본다 2건)이 그렇다.

## 5. 초록 결과

- 전체: **1448 passed** (10.25s, `umask 022`). 실패와 오류는 없다. oracle 683개, unit 765개다.
- 통합 전 작업 트리: 4 failed, 1439 passed. 4건은 §2.1에서 고쳤다. 늘어난 테스트 5개는 통합 단계 unit 테스트다(새 파라미터 3, 새 함수 1, CLI 1).
- 빌더들이 보고한 숫자(1310 passed / 3 failed, 1362 / 5, oracle 679 / 4)는 각자 다른 시점의 작업 트리에서 나온 값이다.

## 6. 바뀐 기존 테스트와 근거 Oracle 줄

테스트 작성자가 바꿨다. 통합 담당은 근거 줄을 매니페스트에서 직접 확인했고, 예전 기대값이 v.5 구현에서 빨강이 되는 것을 (c)·(d)에서 봤다.

| 테스트 | 바뀐 것 | 근거 Oracle 줄 |
|---|---|---|
| `test_oracle_matching.py::test_prov_m2_default_strategy_comes_from_config` | 기대하는 기본 전략: `relevance_plus_diversity` → `relevance_with_distance_bonus`. max 3에서 뽑히는 집합은 같다 | §5.4 "MUST-M2 \| 기본 전략 `relevance_with_distance_bonus` (v.5, 오너 결정 "먼 분야에 가산점")", §2 "먼 분야에 가산점 \| MUST-M2 (v.5, PROV-M2 대체)" |
| `test_oracle_tiers.py::test_must_t1_members_truncated_by_relevance_and_flagged` | Free 한도 3에서 잘리는 후보: F → A2. F 0.36 + 0.3 × 1.0 = 0.66, A2 0.56 + 0 = 0.56, B·C 0.70. Pro 부분은 그대로다 | §5.4 MUST-M2 "자격 있는 후보는 **점수 = 관련도 + `distance_bonus`(config) × 거리** 순으로 고른다". **MUST-T1의 "커널당 수는 상위 관련도 순으로 잘라내고"는 v.5 전 문구라 MUST-M2와 어긋난다. 오너가 정리해야 한다** |
| `test_oracle_exposure.py::test_never_02_private_switch_effects` | withheld B를 실제 subbrain_id로 찾지 않는다. `withheld: true` 항목에 비어 있지 않은 withheld_ref가 하나만 있고, user_a의 canal_get에 실제 B ID가 없는지 본다 | §5.5 NEVER-11 "`canal_get`의 비공개 항목은 실제 ID 대신 그 커널 안에서만 통하는 불투명 핸들(`withheld_ref`)을 쓰고", §9 "(v.5) `canal_get` 비공개 항목의 `withheld_ref`" |
| `test_oracle_v4_exposure.py::test_never_02_v4_host_switched_private_is_withheld_in_canal_get` | 비공개 호스트에도 같은 변경을 했다. 주인이 아닌 user_b·c·e는 withheld_ref를 보고 실제 A ID는 보지 못한다. 주인 부분은 그대로다 | 같은 NEVER-11·§9 줄과 "호스트가 비공개면 델타브레인의 최상위 호스트 subbrain_id도 보이지 않으며" |
| `_v4.py::canonical` (v4 NEVER-11 동일 세계 비교 도우미) | `token_keys`에 `withheld_ref`를 더했다. 마스킹된 참조 안의 문자열 `subbrain_id`·`node_id`는 `<MASKED>`로 바꾼다. 이 처리가 없으면 v.5를 지킨 델타브레인별 불투명 값 때문에 v4 테스트가 엉뚱한 이유로 깨진다. 핸들끼리 엮이지 않는지는 v5 파일이 따로 시험한다 | NEVER-11 "실제 subbrain_id·version·node_id를 보이지 않고" |
| (확인만) 토큰 길이 | 바꾼 oracle 테스트가 없다. `test_oracle_crypto.py`가 보는 것은 API 토큰 길이로, 이 건과 관계없다 | NEVER-11 "토큰 길이는 주인 ID 길이와 무관하게 일정하다" |

새 oracle 파일은 세 개다. `test_oracle_v5_matching.py`(MUST-M2, 48개)는 덤으로 v.5 밖의 계약 고정 1개를 담는다: `test_must_m1_relevance_fields_are_node_tags_labels_and_summaries_only`. `test_oracle_v5_unlinkability.py`(NEVER-11 v.5, 19개)와 `test_oracle_v5_file_modes.py`(MUST-E3, 9개, umask 022 강제)가 나머지 둘이다.

## 7. 사보타주 (통합 변경 되돌리기)

변이마다 작업 트리 사본을 새로 만들고 통합 변경 하나만 되돌렸다. 그다음 `tests/oracle`, `test_unit_mcp.py`, `test_unit_matching.py`(810개)를 돌렸다. 변이 없는 작업 트리는 모두 통과한다.

| 변이 | 되돌린 것 | 결과 | 잡은 테스트 |
|---|---|---|---|
| S1 | 관련도 필드에 도메인·제목·엣지 요약을 다시 넣음 | **빨강** 4 | oracle 3 (`..._relevance_fields_...`, `..._never_selects_below_tau[10-Q-02-None / -default]`) + unit 1 |
| S2 | 기본 전략이 `candidates`를 점수 순으로 제자리 재정렬 | **빨강** 5 | oracle `test_must_m1_q01_selects_only_relevant_members_with_evidence` + unit 4 |
| S3 | canal_open members를 `result.candidates`(관련도) 순으로 | **빨강** 1 | oracle `test_must_m2_v5_canal_open_q01_expert_host_lists_b_and_c_above_a2` |
| S4 | match-explain 표를 envelope 순서로 | **빨강** 1 | unit `test_match_explain_table_shows_score_and_ranks_by_the_strategy` |

빌더 변경에 대한 사보타주는 보고된 대로다. 테스트 작성자는 누출 6종을 모두 잡았다. Builder M은 matching을 다섯 군데 깨뜨렸고 모두 잡혔다. 통합 담당은 이 둘을 다시 돌리지 않았다. 대신 §4 (c)에서, v.5 이전 src에서는 새 oracle 테스트가 빨강이라는 것을 직접 봤다.

## 8. 스모크

`zsh $I/smoke.sh $I`. `umask 022`인 새 scratch 디렉터리에서 실제 콘솔 스크립트(`.venv/bin/opencanal`)를 돌렸다. 출력은 `$I/smoke_out.txt`에 있다. 토큰은 출력과 이 문서에 적지 않았다.

### 8.1 파일 권한 (`stat -f %Lp`)

| 시점 | `data/` | `data/keys/` | `opencanal.db` | `-wal` | `-shm` | `-journal` | `master.key` |
|---|---|---|---|---|---|---|---|
| `init-db` 직후 (디렉터리를 init-db가 새로 만듦) | 700 | 700 | 600 | 없음 | 없음 | 없음 | 600 |
| `seed-fixtures` 뒤 (7개 fixture, 사용자 6명) | 700 | | 600 | 없음 | 없음 | 없음 | |
| `chmod 644` 뒤 `match-explain`으로 다시 엶 | | | 644 → **600** | 없음 | 없음 | | |
| `serve` 실행 중 (DB 열림) | 700 | | 600 | **600** | **600** | 없음 | |
| SIGTERM 뒤 (종료 코드 143) | 700 | | 600 | 없음 | 없음 | 없음 | |

umask 022였으므로, MUST-E3 처리가 없다면 디렉터리는 755, 파일은 644가 됐을 것이다. §4 (c)의 기준선 실패 메시지가 바로 그 값을 보여 준다.

### 8.2 `match-explain` (user_a, Pro, 호스트 A, max_members 6)

Q-01 "모듈러 건축의 현장 조립 오류를 줄일 아이디어". `query_mode_used: topic`, `strategy: relevance_with_distance_bonus`, `tau: 0.200`, `truncated: False`.

| rank | fixture | 제목 | relevance | distance | score | matched_terms | selected | reason |
|---|---|---|---|---|---|---|---|---|
| 1 | C | 단백질 자기조립과 오류 교정 | 0.400 | 1.000 | 0.700 | 조립, 오류 | yes | selected_score |
| 2 | B | 퍼즐 게임 블록 설계 원칙 | 0.400 | 1.000 | 0.700 | 조립, 오류 | yes | selected_score |
| 3 | A2 | 목조 모듈러 주택 설계 메모 | 0.560 | 0.000 | 0.560 | 모듈러, 건축, 현장 | yes | selected_score |
| 4 | D | 동네 빵집 단골 만들기 | 0.000 | 1.000 | 0.000 | | no | below_tau |
| 5 | X | 사내 보안 점검 체크리스트 | 0.000 | 1.000 | 0.000 | | no | below_tau |

B와 C는 점수와 관련도가 모두 같다. 그래서 순서는 subbrain_id 오름차순으로 정해진다. 이번 실행에서는 C의 무작위 ID(`sb_54a3…`)가 B(`sb_68e3…`)보다 앞섰다. MUST-M2의 "Q-01은 B·C가 A2보다 위"와 맞는다.

Q-02 "내 두뇌를 평가해줘". `query_mode_used: whole_host`(호스트 태그·라벨 36개 용어), `truncated: False`.

| rank | fixture | relevance | distance | score | matched_terms | selected | reason |
|---|---|---|---|---|---|---|---|
| 1 | A2 | 1.000 | 0.000 | 1.000 | 모듈러, 건축, 현장, 품질, 상세, 시공, 치수, bim, 공장, 모듈, 관리, 유닛 | yes | selected_score |
| 2 | C | 0.450 | 1.000 | 0.750 | 조립, 오류, 유닛 | yes | selected_score |
| 3 | B | 0.400 | 1.000 | 0.700 | 조립, 오류 | yes | selected_score |
| 4 | D | 0.000 | 1.000 | 0.000 | | no | below_tau |
| 5 | X | 0.000 | 1.000 | 0.000 | | no | below_tau |

§9 "(v.5) 주제 없는 질의(Q-02)에서는 A2(1.00)가 여전히 위다"와 맞는다.

### 8.3 관련도 필드 변경의 fixture 영향 (`$I/compare_fields.py`)

호스트 A, 후보 A2·B·C·D·X(공개)로 비교했다. 변경 전(제목·도메인·엣지 요약 포함)과 변경 후(노드 태그·라벨·요약만)의 relevance·distance·score·selected를 Q-01, Q-02, Q-02a, Q-03, QK에서 max 3과 10으로 뽑아 보니 모두 같았다.

| 질의 | A2 | B | C | D·X |
|---|---|---|---|---|
| Q-01 | 0.56 / 0.56 | 0.40 / 0.70 | 0.40 / 0.70 | 0 / 0 |
| Q-02, Q-02a (whole_host) | 1.00 / 1.00 | 0.40 / 0.70 | 0.45 / 0.75 | 0 / 0 |
| Q-03 | 0 | 0 | 0 | 0 |

(칸 = relevance / score.) 차이는 문서 제목이나 도메인에만 질의 용어가 있는 후보에서만 난다. 예를 들어 oracle의 W_LABEL은 Q-02 whole_host에서 0.36이던 관련도가 0.16(τ 미만)으로 내려간다.

## 9. 남은 위험과 오너 확인이 필요한 것

**통합 단계 해석 (오너가 거부할 수 있다)**
1. 관련도 필드를 노드 태그·라벨·요약으로 한정했다. `subbrain_search`도 같은 `score_relevance`를 쓰므로, 제목·도메인·엣지 요약에만 있는 낱말로는 더 이상 검색되지 않는다. fixture와 golden 질의 결과는 바뀌지 않는다(§8.3). 오너가 제목·도메인을 넣기로 하면, 테스트 작성자가 `test_must_m1_relevance_fields_*`를 빼고 `test_must_m2_v5_never_selects_below_tau`의 기준 공식을 바꿔야 한다. 그 뒤에 구현을 되돌린다.
2. `MatchResult.candidates`는 모든 전략에서 관련도 순이다(`models.py`). match_explain envelope의 `candidates`도 관련도 순이고, 순위 순으로 다시 정렬하는 것은 CLI 표뿐이다. MCP 클라이언트가 match_explain을 직접 읽으면 `score`로 정렬해야 순위를 볼 수 있다.
3. canal_open `members[]`(그리고 저장되는 커널 멤버)의 순서는 전략의 순위(기본은 점수)다. 잘리는 후보가 없을 때 순위가 드러나는 곳은 이것뿐이다.

**테스트 작성자 해석 (보고 그대로, 오너가 거부할 수 있다)**: 점수 동점일 때 subbrain_id는 오름차순으로 비교한다(Oracle은 방향을 말하지 않는다). Q-02, max 1에서는 다양성 보장 때문에 C 하나만 뽑힌다(A2가 먼저 오는 것은 자리가 2개 이상일 때 보인다). 마스킹된 참조는 실제 version도 숨긴다. withheld_ref는 커널마다 기여자당 값 하나이고, 그 커널 참여자 모두에게 같다. 키 파일이 든 디렉터리도 "opencanal이 만드는 데이터 디렉터리"(0700)로 본다.

**빌더 계약 변경 (TASK-001 반영 필요)**
- canal_get에서 주인이 아닌 사람이 보는 비공개 항목은 정확히 `{"withheld": true, "withheld_ref": "wr_<22자>"}`다. `subbrain_id`·`version` 키는 아예 없다. 호스트가 withheld면 `canal.host_subbrain_id`와 `host_version` 대신 `canal.host_withheld_ref`가 온다.
- deltabrain_get·export: 호스트가 비공개이고 보는 사람이 주인이 아니면 `host_subbrain_id`가 null이다.
- `Store.create_user`는 64자를 넘거나 UTF-8로 인코딩되지 않는 ID를 `INVALID_ARGUMENT`로 거부한다. 64자를 넘는 기존 사용자가 있으면 그 사람의 기여가 마스킹된 뷰는 `INTERNAL`이 된다. v0 DB는 새로 만드는 것이라 이전 작업은 넣지 않았다.
- `contributor_token` 형식이 바뀌어 예전 토큰은 복호화되지 않는다. 토큰은 볼 때마다 계산하고 저장하지 않으므로 옮길 데이터가 없다.
- 다른 OS 사용자가 소유한, 권한이 넓은 DB 파일은 좁힐 수 없다. 그래서 열지 않고 `PermissionError`로 끝난다(fail closed). 이미 있는 디렉터리(예: 이미 있는 `data/` 0755)의 모드는 바꾸지 않는다. MUST-E3는 "opencanal이 만드는" 디렉터리만 0700으로 정한다.
- 새 공개 API: `matching.in_rank_order`, `matching.RANK_KEYS`, `matching.candidate_score`, `REASON_SELECTED_SCORE`(`"selected_score"`), `crypto.withheld_ref`, `crypto.make_private_dirs`, `Store.withheld_ref`.

**낡은 고정 문서 (통합 담당은 고치지 않았다)**
- `tasks/TASK-001.md` 24행: 수용 기준에 "PROV-M2(잠정)"가 있다. 26행: 정본이 아직 v2026-10-06.4다. 55행: canal_get의 withheld 행을 `{subbrain_id, version, withheld:true}`로 적고 있다.
- `docs/DECISIONS.md` D-003(31행): 아직 "`relevance_plus_diversity`(기본)와 `relevance_only` 두 전략"이라고 적고 있다.
- `docs/oracle/ORACLE_MANIFEST.md` MUST-T1: "커널당 수는 상위 관련도 순으로 잘라내고"가 MUST-M2(점수 순)와 어긋난다(§6).

**기타**
- §10의 품질 휴리스틱 3건(내용 없는 rationale, 근사 중복, 라벨 재조합)은 오너 결정대로 넣지 않았다. HUMAN-01 평가 10개가 모인 뒤에 다룬다.
- 하네스 주의: CLI 하위 프로세스를 띄우는 oracle 테스트는 `PYTHONPATH`가 없으면 venv에 editable로 설치된 저장소 src를 시험한다. 다른 체크아웃에서 기준선을 돌릴 때는 §3처럼 export해야 한다.
- 모듈 크기가 시작 상한(약 600줄)을 넘는다: store.py 1044줄, service.py 859줄, cli.py 678줄. matching.py는 382줄이다.
- rollback: 스키마 변경은 없다. 작업 트리 변경을 버리면 `0699aa9`로 돌아가지만, 그러면 config의 기본 전략이 없어 canal_open이 `INTERNAL`이 된다(§4 (a)). config를 되돌리는 것은 오너 몫이다.

## 10. 적대 확인 (v.5 판정 확인 파인딩 2건)

> Builder-integrator가 2026-10-06에 남긴 기록이다. 대상은 반박되지 않은 판정 파인딩 `N11-V5-ORDER-1`(high, NEVER-11 v.5)과 `E3-1`(medium, MUST-E3 v.5)이다. 커밋하지 않았다.
> 작업 파일: `$F` = `$V/fixer-n11-e3/` (저장소 밖). 수정 전 사본은 `$F/pre/repo`(수정 직전 작업 트리), 수정 후 사본은 `$F/post/repo`다. 판정자 스크립트는 고치지 않고 복사해서 썼다(`$V/judge-never11/repro_order_leak.py`, `check_host_and_owner.py`, `$V/refute-n11-order/refute_order.py`). E3-1 스크립트(`$F/e3_cli.sh`, `$F/e3_store.py`)는 `$V/e3-perms/repro_f1_symlink.sh`, `repro_f1_store_symlink.py`를 옮기면서 세 군데를 바꿨다. 시험할 src를 인자로 받고(`PYTHONPATH`로 지정하고 import 경로를 단언한다), serve 포트를 유효한 값으로 고쳤다(원본 `18${UM}7`은 180227이 되어 serve가 바로 끝났다). 대상 디렉터리가 없는 경우(A')도 더했다.

| finding id | 재현 | 수정 전 | 수정 후 |
|---|---|---|---|
| N11-V5-ORDER-1 | `cd $F/<pre\|post> && PYTHONPATH=$F/<pre\|post>/repo/src:$F/<pre\|post>/repo .venv/bin/python repro_order_leak.py` (세계 40개, 매 세계 무작위 ID). E1: Q-01, 호스트 A, C 비공개, 보는 사람 user_e. E2: 같은 호스트·질의로 커널 2개, B·C 비공개, 위치로 withheld_ref 짝짓기. E3: E2와 같되 두 번째 커널 호스트 A2(user_e), 보는 사람 user_a. E4: 멤버 목록. 보조: `check_host_and_owner.py`(호스트 A 비공개), `refute_order.py 40`(E5) | E1: "withheld가 B 앞" = "실제 sid_C < sid_B"가 **40/40**, 두 경우가 모두 나옴 (실제 ID 1비트 누출). E2: 위치 짝짓기 정답 **40/40**. E3: **40/40**. E4: `B(0.4, 1.0), WITHHELD, A2(0.56, 0.0)` (숨긴 점수가 0.56~0.70 사이로 묶임). 호스트 비공개: `WITHHELD, B(rel 0.4), A2(rel 0.56)` (관련도가 더 높은 A2가 아래 = 숨긴 거리 누출). 주인 확인 6개 모두 True | withheld는 늘 보이는 멤버 뒤에 온다. E1: "withheld가 B 앞" **0/40** (두 번 실행 모두. 판정자 지표는 이제 무작위 ID 비교만 세므로 15/40, 19/40, refute 스크립트 27/40이고, "both outcomes seen: False"). E2: **16/40, 21/40** (refute 18/40). E3: **23/40, 19/40** (refute 19/40). 우연 기준은 약 20/40이다. E4: `B, A2, WITHHELD` (스크립트가 찍는 "sits above A2" 설명은 고정 문구라 이제 출력과 맞지 않는다). 호스트 비공개: `A2(rel 0.56), B(rel 0.4), WITHHELD` (보이는 관련도 순). E5: `A2, B, C`. 주인 확인 6개 모두 True |
| E3-1 | CLI: `zsh $F/e3_cli.sh $F/<pre\|post>/repo/src <작업 디렉터리>` (umask 022·002, `data/opencanal.db -> ext/opencanal.db`, 대상 없음. `init-db`, `mcp-stdio`, `serve`를 각각 첫 명령으로 실행). Store: `.venv/bin/python $F/e3_store.py <src> <작업 디렉터리>` (A 대상 없는 심볼릭 링크, A' 대상 디렉터리도 없음, B 기존 DB를 링크로 열고 0644 -wal/-shm을 다른 연결이 붙잡음) | 두 umask 모두: `init-db`가 "(권한 0600)"을 찍지만 `ext/opencanal.db`는 **644**. `mcp-stdio`·`serve` 실행 중 db·-wal·-shm **644/644/644**. Store A: 열린 동안 644×3, 닫은 뒤 644. A': `OperationalError: unable to open database file`. B: db 600, **-shm 644**, -wal 600 (-wal이 600인 이유는 판정자 설명으로는 SQLite가 길이 0 파일에 직접 fchmod한 것이다. 직접 확인하지 않았다) | 두 umask 모두: `init-db` 뒤 `ext/opencanal.db` **600**. `mcp-stdio`·`serve` 실행 중 **600/600/600**. 링크는 링크로 남고, 링크 옆에는 부속 파일이 생기지 않는다. Store A: 열린 동안 600×3, 닫은 뒤 600. A': 새로 만든 `real/`, `real/sub/`는 700이고 파일은 600×3 (동작 변경, 아래). B: **600×3** |

출력: 수정 전 `$F/pre/{order_leak_out,host_owner_out,e3_cli_out,e3_store_out}.txt`, 수정 후 `$F/post/{order_leak_out,host_owner_out,refute_order_out,e3_cli_out,e3_store_out}.txt`.

### 10.1 수정

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/opencanal/service.py` `_canal_get` | 보는 사람에게 숨긴 것이 하나라도 있으면(멤버 withheld **또는** 호스트 withheld) 목록 순서를 다시 정한다. `canal.members`와 `untrusted_data.subbrains`는 같은 순서다. (1) 보이는 멤버가 먼저 온다. 호스트가 보이면 저장된 순위 순서를 그대로 쓴다: 순위를 정한 입력(관련도·거리·ID·version)이 모두 보이므로 새로 드러나는 것이 없다. 호스트가 비공개이고 topic 모드면 `(-관련도, subbrain_id)` 순, whole_host 모드면 관련도도 호스트에서 나온 값이라 `subbrain_id` 순이다. (2) 그 뒤에 withheld 항목을 `withheld_ref` 순으로 둔다. ref는 커널별 PRF라서 커널마다 엮을 수 없는 순열이 된다. 숨긴 것이 없으면(예: 주인이 자기 비공개 서브브레인을 볼 때) 저장된 순위 순서 그대로다. "not even scores" 주석은 순서 설명으로 바꿨다 | 저장 순서(점수 → 관련도 → 실제 subbrain_id)에 withheld를 제자리에 두면 위치가 숨긴 점수 범위를 드러냈다. 동점일 때는 실제 ID 비교를 드러냈고, 그 비교는 모든 커널에서 같아서 위치만으로 withheld_ref를 커널 사이에서 짝지을 수 있었다(NEVER-11 v.5 "어떤 값으로도 … 엮을 수 없다"). 호스트가 비공개면 점수 순서가 숨긴 거리를 드러냈다. 순위 규칙 자체(MUST-M2의 `_score_rank`, `store._canal`의 `ORDER BY rowid`)는 그대로 두었다: MUST-M2는 매칭과 canal_open 순위를 정하는 규칙이고, 고친 곳은 canal_get 뷰다 |
| `src/opencanal/store.py` | `_resolved_db_path(path)` = `Path(os.path.realpath(path))`를 추가했다(대상이 없는 링크도 대상 경로로 풀린다). `_prepare_db_file`은 풀린 경로에서 디렉터리 생성(0700), `O_CREAT\|O_EXCL` 0600 생성, 기존 파일 좁히기, 부속 파일 좁히기를 하고 그 경로를 돌려준다. `Store.__init__`은 그 경로를 `sqlite3.connect`에 넘기고, 열고 난 뒤 부속 파일 재점검도 그 경로에서 한다. `:memory:`는 그대로다 | 링크에 `O_CREAT\|O_EXCL`을 하면 대상이 없어도 EEXIST가 났다. 그 뒤 `_tighten_existing`은 대상이 없어 그냥 돌아갔고, SQLite가 대상을 0644 & ~umask로 만들었다. SQLite는 부속 파일을 풀린 대상 옆에 두는데, 검사는 링크 옆을 봤다. 이제 검사하는 파일과 SQLite가 쓰는 파일이 같다 |
| `tests/unit/test_unit_v5_judge_findings.py` (신규, 18개) | N11 9개: withheld는 저장 순위와 상관없이 맨 뒤(C 먼저·B 먼저 두 저장 순서, 보는 사람 3명). withheld끼리는 커널별 ref 순(호스트가 다른 두 커널). 커널 32개에서 B ref가 앞서는 경우와 뒤서는 경우가 모두 나옴(모두 같을 확률 2^-31). 호스트 비공개 topic → 관련도 순, whole_host → ID 순. 호스트와 멤버가 함께 비공개. 숨긴 것이 없으면 저장 순서 유지(주인 보기 포함). 호스트가 보이면 보이는 멤버의 저장 상대 순서 유지. E3 9개: 대상 없는 링크(절대·상대 대상, umask 000) → 대상과 -wal/-shm 600, 링크 옆 부속 파일 없음. 대상 디렉터리 생성 700. 기존 DB를 링크로 열면 0644 -wal/-shm(다른 연결이 붙잡음) → 600. `_prepare_db_file(link)`가 대상 옆 -wal/-shm/-journal을 좁히고 풀린 경로를 돌려줌. CLI `init-db`(umask 022·002) → 대상 600 | 수정 전 src(`PYTHONPATH=$F/pre/repo/src`)에서 **16 failed, 2 passed**였다(`$F/pre/newtests_on_prefix.txt`). 통과한 2개는 바뀌면 안 되는 동작을 지키는 테스트다(숨긴 것이 없으면 저장 순서 유지, 호스트가 보이면 보이는 멤버 순서 유지) |

고정 파일(`docs/`, `config/`, `fixtures/`, `tests/oracle/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. 시작할 때 수정·미추적 파일 24개의 해시를 떠 두었다(`$F/hashes_start.txt`). 끝에 비교하니 바뀐 것은 `service.py`와 `store.py`뿐이고, 새 파일은 `tests/unit/test_unit_v5_judge_findings.py` 하나다. 내 변경만 담은 diff는 `$F/service.diff`, `$F/store.diff`에 있다.

작업 중 사고 1건: 처음 고칠 때 `_prepare_db_file`에 `return path`를 빠뜨렸다. 그래서 새 테스트를 처음 돌렸을 때 `sqlite3.connect("None")`이 저장소 루트에 `None`이라는 DB 파일을 만들었다. 21:53에 생긴 파일이고, 그 실행에서 6건이 실패했다. 내가 만든 파일이므로 지웠고(`None`만 있었고 -wal/-shm은 없었다), `return`을 넣은 뒤 다시 돌렸다. 그 뒤 전체 실행에서는 그런 파일이 생기지 않았다.

### 10.2 전체 스위트

- 수정 전 (같은 작업 트리, umask 022): **1448 passed**.
- 수정 후 (`.venv/bin/python -m pytest -q -p no:cacheprovider`, umask 022, 테스트 id 정리 뒤 마지막 실행): **1466 passed** (10.39s). 새 unit 테스트 18개가 늘었다. 실패와 오류는 없다. 기존 테스트 가운데 canal_get 멤버를 위치로 고정한 것은 없다: `members"][`로 찾은 곳은 모두 canal_open 응답이다.

### 10.3 Oracle 테스트 빈칸 (플래너가 더할 것. 나는 `tests/oracle`을 고치지 않았다)

1. **NEVER-11 v.5 순서 경로** → `tests/oracle/test_oracle_v5_unlinkability.py`. 지금 `test_never_11_v5_no_contributor_specific_value_is_shared_between_the_canals`는 문자열 값만 비교하고 위치는 보지 않는다. 그래서 수정 전에도 통과했다. 세계 N개(≥32, 매번 새 ID)에서 다음을 확인하는 테스트를 제안한다. 구현 방식에 묶이지 않는 성질이다.
   - (a) Q-01, 호스트 A, C 비공개, 보는 사람 user_e: "withheld 항목이 B보다 앞"과 "실제 sid_C < sid_B"가 N개 모두에서 같거나 N개 모두에서 다르면 실패한다.
   - (b) 같은 호스트·질의로 커널 2개를 열고 B·C를 비공개로 한다. 보는 사람 user_e가 두 커널의 withheld_ref를 목록 위치로 짝지었을 때, 정답 짝(`store.withheld_ref`로만 계산)과 N개 모두 맞거나 모두 틀리면 실패한다.
   - (c) (b)와 같되 두 번째 커널은 user_e가 A2를 호스트로 열고, 보는 사람은 user_a다.
   - (d) 호스트 A 비공개, Q-01: 주인이 아닌 사람이 본 보이는 멤버 순서가 N개 모두에서 숨긴 거리로 계산한 점수 순서(B·C가 A2 위)와 같으면 실패한다.
   - 수정 전 기대값: (a)·(b)·(c) N/N, (d) 늘 점수 순서. 수정 후: 약 N/2이고, (d)는 관련도 순서다.
2. **MUST-E3 심볼릭 링크 DB 경로** → `tests/oracle/test_oracle_v5_file_modes.py` (umask 022). DB 경로가 대상이 아직 없는 심볼릭 링크일 때: (a) CLI `init-db` 뒤 대상 DB가 0600이다. (b) Store(또는 `serve`)가 열려 있는 동안 대상 옆 `-wal`·`-shm`이 0600이다. (c) 기존 DB를 링크로 열 때, 다른 연결이 붙잡고 있는 0644 `-wal`/`-shm`이 대상 옆에 있으면 0600으로 좁힌다. Oracle 문장(MUST-E3 "opencanal이 만들거나 여는 DB 파일과 그 부속 파일")에는 링크 예외가 없다.

### 10.4 남은 위험

- **동작 변경 (E3-1)**: 대상 디렉터리가 없는 링크(A')는 예전에 `OperationalError`로 끝났다. 이제는 대상 쪽 빠진 디렉터리를 0700으로 만들고 DB를 연다. 링크가 아닌 경로에서 빠진 디렉터리를 만드는 것과 같은 규칙(MUST-E3 "opencanal이 만드는 데이터 디렉터리는 0700")이다. `restore`가 링크 경로를 거부하는 것(`lexists`, fail closed)과 `cli._open_store`의 `make_private_dirs(db.parent)`는 그대로다.
- **E3-1 TOCTOU**: `realpath`와 `sqlite3.connect` 사이에, 경로 중간의 디렉터리나 링크를 쓸 수 있는 다른 로컬 사용자가 링크를 바꿀 수 있다. v0는 로컬 단일 사용자이므로 다루지 않았다.
- **NEVER-11 범위**: 고친 것은 canal_get의 순서 경로다. 판정자 반박문이 적었듯, NEVER-02가 보이게 남기는 델타브레인 라벨(보존 내용)은 델타브레인이 있으면 여전히 같은 기여자를 커널 사이에서 엮는 데 쓰일 수 있다. Oracle이 보존 내용을 허용하는 부분(`_retained_strings`)이므로 고치지 않았다. 한 커널 안에서 withheld 개수가 보이는 것은 NEVER-11의 범위 밖이다.
- **canal_get 순서 계약**: 숨긴 것이 있을 때 canal_get 멤버 순서는 순위 순서가 아니다. 순위는 canal_open 응답과 match_explain에 있다. 순서 규칙을 TASK-001의 canal_get 행에 적어 두는 것이 좋다(고정 문서라 고치지 않았다).

## 부록 — 적대 확인 2건을 tests/oracle로 고정 (플래너)

| 파인딩 | Oracle | 새 테스트 (`tests/oracle/test_oracle_v5_gaps.py`) | 실제 트리 | 사보타주 복사본 |
|---|---|---|---|---|
| N11-V5-ORDER-1 | NEVER-11 v.5 (비공개 항목은 보이는 항목 뒤, 핸들 순서) | `test_never_11_v5_withheld_entries_do_not_keep_their_rank_position` | 통과 | 실패 (비공개 항목을 앞에 둔 변형) |
| E3-1 | MUST-E3 v.5 (심볼릭 링크면 실제 파일 기준) | `test_must_e3_v5_symlinked_db_path_yields_0600_real_files` | 통과 | 실패 (`realpath` 제거 변형) |

- Oracle 문구도 맞췄다: MUST-T1은 "선택 전략의 순위(기본: MUST-M2 점수) 순"으로, NEVER-11과 MUST-E3에는 위 규칙을 넣었다.
- 전체 결과(umask 022): **1469 passed**.
