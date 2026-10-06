# CHANGE-003 — Oracle v.4 수정 라운드 통합 기록

> NDSH 부록 B-7 양식. 통합 담당(Integrator)이 2026-10-06에 남긴 기록이다. 사실만 적는다.
> 기준: `docs/oracle/ORACLE_MANIFEST.md` v2026-10-06.4, `tasks/TASK-001.md`, 기준 커밋 `ba7b438`. 커밋하지 않았다.
> 재현·사보타주 작업 파일: `$SP/judge/integrator-v4/` (`$SP` = 이 세션의 scratchpad. 저장소 밖이다).

## 1. 변경 요약 (파인딩 id별)

수정은 병렬 단계에서 빌더 4명(SAN, VAL, SS, CLI)과 테스트 작성자가 했다. 통합 담당은 재현 스크립트 재실행과 TS 사보타주로 결과를 확인했다. "확인" 열의 뜻은 이렇다. **통합자 재현**은 §5의 수정 전·후 재실행으로 직접 봤다는 뜻이다. **빌더 보고**는 빌더 보고만 있고 통합 담당이 따로 재현하지 않았다는 뜻이다.

| id | 고친 곳 | 내용 | 확인 |
|---|---|---|---|
| SAN-1 | `sanitize.py` | 경로 정규식을 다시 썼다. 폴더 이름 안 공백(OneDrive - 회사명, 이름 여러 단어), 끝 폴더 여러 단어, 확장자로 끝나는 여러 단어 파일명을 처리한다. 하위 경로가 있을 때는 루트를 대소문자 구분 없이 잡는다(System, Library, Applications, cygdrive 추가). `/Users/<이름>`은 어디에 있든 잡는다. `//server/share`, `\\?\C:\`, `%VAR%\`, `$HOME/`, `${HOME}/`, `$env:USERPROFILE\`, `~\`도 잡는다. ID 앞의 `n-`, `e-`에 붙은 값도 잡는다 | 통합자 재현 |
| SAN-2 | `sanitize.py` | 모든 텍스트 필드와 ID를 NFKC 정규화한 뒤 `textnorm.strip_invisible`과 제어 문자 제거를 거쳐 가린다. 저장되는 값도 정규화한 텍스트다. 전화번호·주민등록번호 구분자로 유니코드 대시(U+2010~2015, U+2212, U+FE58, U+FE63, U+FF0D)를 받는다 | 통합자 재현 |
| SAN-3 | `sanitize.py` | 전화번호에 `02)`, `(031)`, 구분자 없는 유선, 050x·060·070·080, `00xx` 국제 접두, `+82 010-…`, 대시 양옆 공백, 점 구분을 더했다. 대표번호(15xx·16xx·18xx 목록)는 구분자가 있을 때 잡는다 | 통합자 재현 |
| SAN-4 | `sanitize.py` | 손으로 쓴 보이지 않는 문자 목록을 없애고 `textnorm.strip_invisible`(Cf, 한글 채움, 이형 선택자, CGJ)과 C0·C1 제어 문자 제거를 쓴다. 지운 개수를 `kind="invisible"`로 보고한다 | 통합자 재현 |
| SAN-5 | `sanitize.py` | 노드·엣지 ID도 같은 정규화를 거친 뒤 전체 마스커로 검사한다. 민감하면 `redacted-node-i` / `redacted-edge-j`로 바꾼다. 엣지 source/target도 정규화한 뒤 찾는다. 정규화 뒤 겹치는 ID는 `IMPORT_INVALID`다 | 통합자 재현 |
| SAN-6 | `sanitize.py` | 스킴 없는 `host.TLD[:port]/path`(소문자 TLD 허용 목록), IPv4·localhost에 포트나 경로가 붙은 형태를 URL로 가린다 | 통합자 재현 |
| GAP-1 | `sanitize.py` | 주민등록번호(구분자 있으면 외국인등록번호 5~8 포함) → `[REDACTED:RRN]`, kind `rrn`. 비밀값(`oc_`, `ocm_`, `sk-`, AKIA/ASIA, `gh[pousr]_`, `github_pat_`, `xox?-`, AIza, `sk_live_`, JWT, PEM 개인 키 블록, `password=` 등 키-값) → `[REDACTED:SECRET]`, kind `secret` | 통합자 재현 |
| L1-5 (결정적 절반) | `validator.py` | MUST-Q7 v.4. 각 엣지의 정규화 rationale에서 양 끝 노드 라벨(정규화)을 자리표시자 `<>`로 바꾼다(긴 라벨부터). 정규화 텍스트가 같거나, 바꾼 뒤의 뼈대가 같으면 반복으로 센다 | 통합자 재현 |
| L1-7 | `validator.py`, `protocol.py` | NO_EMERGENCE·HOST_NOT_TOUCHED 메시지와 프로토콜 규칙·지시 8·10·11을 v.3 정의로 고쳤다. 창발과 호스트 판정은 양 끝 노드 출처로만 하고, 엣지 직접 출처는 근거다. NOT_NOVEL은 창발 여부와 방향에 상관없이 모든 source–source 엣지에 적용된다. TEMPLATED는 라벨을 치환해 비교하고, 정규화 정의에 보이지 않는 문자가 들어간다 | 통합자 재현 |
| EXP-1 | `store.py`, `service.py` | NEVER-11 v.4. `_viewer_identities`·`_viewer_stats`로 보는 사람에게 보이는 신원 기준 통계를 낸다. deltabrain_get·list·rate·export가 이 통계를 쓴다. rate의 NOT_FOUND와 NOT_EMERGENT_EDGE도 보는 사람의 뷰로 판정한다. 저장된 통계는 바뀌지 않는다 | 통합자 재현 |
| EXP-4 | `service.py` | NEVER-09 v.4. deltabrain_get 최상위 `stats`에는 숫자만 둔다. 엣지 ID 목록과 `ratings`는 `untrusted_data`로 옮기고, 최상위에 `rating_summary`를 새로 둔다. deltabrain_rate의 `edge_id`도 `untrusted_data`로 옮긴다. canal_open·canal_get `members[]`에서 `owner_display`를 뺀다. canal_get의 `matched_terms`는 `untrusted_data.subbrains[]`로 옮긴다 | 통합자 재현 |
| EXP-5 | `service.py` | withheld 행은 `{subbrain_id, version, withheld}`만 남긴다. 호스트가 withheld면 보이는 멤버 행에서도 호스트에서 나온 값(distance, whole_host일 때 relevance·matched_terms)을 뺀다 | 통합자 재현 |
| TS-1 (src 확인) | 없음 | src는 이미 맞았다. 테스트로 고정했다 | §6 사보타주 |
| TIER-1 | `store.py`, `service.py` | 모든 Store 쓰기를 `_write_txn`(BEGIN IMMEDIATE)으로 감싼다. `create_canal(..., *, canals_per_month=None)`과 `set_visibility(..., *, max_public=None)`는 같은 트랜잭션 안에서 세고 `LIMIT_EXCEEDED`를 낸다. 서비스의 사전 카운트는 빠른 경로로만 남는다 | 통합자 재현 |
| CRY-1 | `store.py`, `cli.py` | `Store.restore_bytes`는 `<db>`, `-wal`, `-shm`, `-journal`이 하나라도 있으면(lexists) 거부한다. 쓰기는 임시 파일(0600) → fsync → `os.link`다. `cmd_restore`는 키를 읽기 전에 같은 검사를 하고, 운영자용 안내를 출력한다. 이미지에 `PRAGMA quick_check`를 돌린다. `serve`는 SIGTERM을 받으면 Store를 닫는다(종료 코드 143). 그래서 -wal/-shm이 남지 않는다 | 통합자 재현 |
| TIER-2 | `mcp_server.py`, `app.py`, `cli.py` | 로그 마스킹을 넓혔다. 요청 대상 경로의 두 번째 세그먼트부터와 쿼리 값, `/mcp/` 뒤(대소문자 무관, 이중 슬래시), `oc_` 토큰 모양을 가린다. 필터를 uvicorn·opencanal·root 핸들러와 `logging.lastResort`에 설치하고, `mcp-stdio`에도 설치한다 | 통합자 재현 |
| L1-2 | (src 변경 없음) | `textnorm.normalize` v.4(오너, `ba7b438`)로 고쳐졌다 | 통합자 재현 (dce60c1 대비) |
| MATCH-2 | (src 변경 없음) | `config/matching.json` 불용어 추가(오너, `ba7b438`)로 고쳐졌다 | 통합자 재현 (dce60c1 대비) |
| TS-1~TS-8 | `tests/oracle/_v4.py`, `tests/oracle/test_oracle_v4_*.py` 6개 (테스트 작성자) | 440개 테스트 추가. 기존 oracle 164개는 그대로다 | §6 사보타주 |

### 통합 단계에서 직접 바꾼 것

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/opencanal/sanitize.py` | `_is_year_range`가 연도 표시(`년`/`年`, 앞에 공백 0~1개)가 바로 뒤에 있을 때만 대표번호 모양을 연도 범위로 보고 남긴다 | 이전에는 앞 숫자 < 뒤 숫자 ≤ 2100이면 무조건 남겼다. 그래서 `1588-2000`, `1644-2000`, `1577-1600`, `1661-2024` 같은 실제 대표번호가 가려지지 않았다(SAN 빌더 메모 5). NEVER-04 v.4는 대표번호를 명시한다. fail closed로 고쳤다. 대신 연도 표시 없는 `1800-1900`은 이제 전화번호로 가려진다 |
| `src/opencanal/service.py` | `subbrain_import` 도구 설명이 실제 마스킹 범위를 말하게 고쳤다: 보이지 않는 문자, 주민등록번호, 비밀값, ID 포함 | SAN 빌더 메모 9. 처음 쓴 "removed"는 D-005 금지어 단위 테스트(`remove`)에 걸려 "stripped"로 바꿨다 |
| `tests/unit/test_unit_sanitize_v4.py` | 비마스킹 사례 `"1800-1900"`을 `"1800-1900년대"`, `"1800-1900 년"`으로 바꿨다. `test_representative_number_that_looks_like_a_year_span_is_masked`(6건)와 `test_year_span_exemption_needs_a_year_marker`를 추가했다 | 위 변경을 고정한다 |
| `evidence/CHANGE-003.md` (신규) | 이 문서 | |

`fixtures/brains/*.json` 전체를 가져와 content_hash와 redactions를 비교했다. SAN 빌더의 수정 전·후 스냅샷과 바이트 단위로 같다.

고정 파일(`docs/`, `config/`, `fixtures/`, `tests/oracle/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. `git diff HEAD`로 보면 이 경로들에 차이가 없다. `tests/oracle/`의 새 파일은 테스트 작성자가 만든 미추적 파일이다. `matching.py`와 `crypto.py`는 이번 라운드에 바뀌지 않았다. 통합하는 동안 다른 에이전트가 src를 바꾸지 않았다는 것도 확인했다. 시작할 때와 끝날 때 해시를 비교하니, 차이는 통합 담당이 고친 두 파일뿐이었다.

## 2. 실행 명령

```bash
# 자동 검사 (저장소 루트)
.venv/bin/python -m pytest -q -p no:cacheprovider

# 수정 전 트리 (scratchpad, 저장소 밖)
git archive dce60c1 | tar -x -C $I/trees/before_v3   # judge가 돌린 트리 (v.3)
git archive ba7b438 | tar -x -C $I/trees/before_v4   # v.4 계약 + 수정 전 src
# 재현 스크립트 사본: python $I/mkrepro.py   (judge/<dir>/의 원본은 고치지 않았다. 경로만 트리별로 바꾼 사본)
# TS 사보타주:       python $I/run_ts_sabotage.py  (작업 트리 rsync 사본에 변이 1개씩, tests/oracle 실행)
```

`$I` = `$SP/judge/integrator-v4`. 출력은 `$I/out/`에 있다.

## 3. 빨강 기준선 (통합 전)

- 명령: `.venv/bin/python -m pytest -q -p no:cacheprovider`
- 결과: **1277 passed, 0 failed, 0 errors** (8.90s). oracle 604개(기존 164 + v4 440), unit 673개.
- 빨강은 재현되지 않았다. 통합을 시작할 때 빌더와 테스트 작성자의 작업이 이미 끝나 있었다. 각자 보고한 일시적 실패는 통합 담당이 직접 보지 못했다.
  - 테스트 작성자: 18:58 KST 무렵 `test_never_04_v4_value_is_masked_everywhere[path_home|secret_oc|secret_ocm|secret_sk|secret_slack × node_id|edge_id]`와 같은 5종의 `..._service_import_preview_store_and_published_copy`, 모두 15건이 실패했다. ID 앞의 `n-`/`e-`에 붙은 값이 가려지지 않았다. sanitize.py가 19:00과 19:03에 바뀐 뒤 통과했다.
  - CLI 빌더: `tests/unit/test_unit_sanitize.py::test_ordinary_text_is_not_masked[1588-1234]` 실패. SAN 빌더가 대표번호를 마스킹 대상으로 옮기면서 해소됐다.
- 이 테스트들이 실패할 수 있다는 근거: §6 사보타주에서 22개 변이 중 18개가 scratch 사본에서 바로 빨강이었다. 1개(T05)는 stdio 하위 프로세스가 변이를 실행하도록 하니 빨강이었다.

## 4. 초록 결과 (통합 후)

- 전체: **1285 passed** (8.99s). 실패와 오류는 없다.
- oracle 604, unit 681. unit 8개는 §1의 통합 단계 단위 테스트다(새 파라미터 6, 새 테스트 1, 비마스킹 사례 1개 추가).

## 5. 재현 스크립트 재실행 표

수정 전은 `ba7b438` 트리다. L1-2와 MATCH-2만 `dce60c1` 트리를 썼다. 둘 다 `ba7b438`에서 고정 파일이 바뀌면서 고쳐졌기 때문이다. 수정 후는 현재 작업 트리다. 스크립트는 judge 원본의 경로만 바꾼 사본이고, 원본은 손대지 않았다. 원본이 옮겨진 필드를 읽다가 멈춘 경우에는 같은 시나리오를 새 위치에서 읽는 적응본(`*_adapted.py`)을 따로 돌렸다.

| id | 재현 스크립트 | 수정 전 | 수정 후 | 근거 |
|---|---|---|---|---|
| EXP-1 | `exposure/probes/p1_emergence_unmasks_private_owner.py` (+ `p1_adapted.py`) | **재현.** user_c가 보는 값이 두 세계에서 갈렸다. B2 주인이 user_b(B와 같은 사람)인 세계에서는 owners_involved 3, e11 비창발, rate(e11) `NOT_EMERGENT_EDGE`였다. user_f인 세계에서는 4, 창발, ok였다. 적응본 기준으로 7개 응답 중 4개(get, list, rate e11, 평가 뒤 get)가 달랐다 | **재현 안 됨.** 원본은 `stats.emergent_edge_ids`를 읽다 KeyError로 멈췄다(필드 이동). 적응본에서는 두 세계 모두 owners_involved 4, e11 창발, rate(e11) ok였다. ID·토큰·시각을 자리표시자로 바꾸고 목록을 다중집합으로 비교하니 7개 응답이 모두 같았다. 호스트의 실제 통계는 여전히 3 대 4로 다르다 | `out/*.p1_adapted.txt` |
| EXP-4 | `exposure/probes/p7_text_outside_untrusted.py` | **재현.** 주입 문자열이 봉투 밖 3곳(`stats/emergent_edge_ids/0`, `stats/host_touching_emergent_edge_ids/0`, `ratings/edges/0/edge_id`)에 있었다. canal_get 최상위 `canal.members[0]`에는 `owner_display` 'Chaeyoung Yoon'과 `matched_terms`가 있었다 | **재현 안 됨.** 4곳 모두 `untrusted_data/...` 아래에 있다. `canal.members[0]`에 owner_display와 matched_terms가 없다 | `out/*.p7_text_outside_untrusted.txt` |
| EXP-5 | `exposure/probes/p4_withheld_matched_terms.py` (+ `p4_adapted.py`) | **재현.** withheld C 행에 matched_terms ['조립','오류','유닛'], relevance 0.45, distance 1.0이 있었다 | **재현 안 됨.** 원본은 `matched_terms` KeyError(필드 제거). 적응본에서 withheld 행은 `{subbrain_id, version, withheld}`뿐이고, `canal` 최상위에 matched_terms가 없다 | `out/*.p4_adapted.txt` |
| TIER-1 | `tier/probe_race_canal_limit.py 5 5` | **재현.** 5/5 시행에서 한도를 넘었다(14/10) | **재현 안 됨.** 0/5. 매번 1개만 ok, 4개 `LIMIT_EXCEEDED`, 10/10 | `out/*.race_canal.txt` |
| TIER-1 | `tier/probe_race_public_limit.py 20` | **재현.** 20/20 초과(공개 2/1) | **재현 안 됨.** 0/20 | `out/*.race_public.txt` |
| TIER-1 | `tier/probe_race_transports.py 4` (실제 HTTP + stdio) | **재현.** 월 커널 4/4 초과(11/10). 공개 수는 0/4 | **재현 안 됨.** 0/4, 0/4 | `out/*.race_transports.txt` |
| TIER-2 | `tier/probe_access_log.py` | **재현.** 전체 토큰이 든 로그 4줄(`/mcp//`, `/x/`, `/`, `/MCP/`). 종료 뒤 `-wal`, `-shm`이 남았다 | **재현 안 됨.** 0줄. 13개 요청이 모두 잘린 형태(`oc_3IU…`, `%20oc_…`)로 기록됐다. SIGTERM 뒤 `-wal`, `-shm`이 없다 | `out/*.access_log.txt`, `w_log/` |
| CRY-1 | `sanitize-crypto/restore_stale_wal.py` | **재현.** CLI restore가 종료 코드 0으로 끝났다. 복원 DB에 `user_mallory`가 있고 Mallory 토큰이 인증됐다 | **재현 안 됨.** 종료 코드 1. 남은 `o.db-wal`, `o.db-shm`을 이름으로 대며 거부하고 운영자 안내를 낸다 | `out/*.restore_stale_wal.txt` |
| CRY-1 | `refuter-cry1/repro_wal.py` (A~E) | A·B 재생(mallory, 필러 사용자), C `database disk image is malformed`, D 정상, E 재생 | A·B·C 거부(종료 1), D 정상. **E는 여전히 재생된다**(새 경로로 복원한 뒤 운영자가 옛 경로로 `mv`). restore가 볼 수 없는 단계라서 CLI는 복원 뒤 안내만 출력한다 | `out/*.repro_wal.txt` |
| SAN-1 | `sanitize-crypto/probe_paths_phones.py` (PATH 24건), `e2e_leak.py` | **재현.** firmlink, `Macintosh HD/Users`, `./Users`, `../Users`, `/users`, `/USERS`, `/HOME`이 그대로 남았다. `Hong Gil Dong`, `My Brain Vault`, iCloud `My Second Brain`, `OneDrive - Logotekton Inc`는 꼬리가 남았다 | **재현 안 됨.** 파인딩이 든 사례는 모두 `[REDACTED:PATH]`로 통째로 가려진다. 남은 것: `~kim`, `Users/kim/…`, `home/kim/…`, `C:Users\kim`(앞 슬래시·구분자 없는 상대 형태). `Macintosh HD`, `.`, `..` 접두는 남지만 `/Users/<이름>`은 남지 않는다 | `out/*.probe_paths_phones.txt` |
| SAN-2 | `e2e_leak.py`, `probe_mask.py` | **재현.** e2e에서 17/17 값이 user_a의 subbrain_get에 보였다 | **재현 안 됨.** 0/17. 전각 숫자·＠·／·：, 유니코드 대시를 모두 가린다 | `out/*.e2e_leak.txt` |
| SAN-3 | `probe_paths_phones.py` (PHONE 24건) | **재현.** `02)…`, `031)…`, `0311234567`, `0212345678`, `021234567`, `0505-…`, `0507-…`, `0082-…`, `010 - 1234 - 5678`이 가려지지 않았다 | **재현 안 됨.** 9건 모두 가려진다. 파인딩 밖 잔여: `010_1234_5678`, `010~1234~5678`, `010 12 34 56 78`, `010-12-345-678`, `1012345678`, `010/1234/5678`(probe_mask) | 같은 파일 |
| SAN-4 | `probe_invisible.py` | **재현.** 10개 code point 모두 전화·이메일·경로가 남았다(보고는 url뿐) | **재현 안 됨.** 생존 0. kind `invisible`을 보고한다 | `out/*.probe_invisible.txt` |
| SAN-5 | `probe_ids.py` | **재현.** 노드 ID 2개, 엣지 ID 1개에 값이 남고 보고가 없었다 | **재현 안 됨.** `redacted-node-0..2`, `redacted-edge-0`. `invisible`과 kind를 보고한다 | `out/*.probe_ids.txt` |
| SAN-6 | `probe_mask.py` (url_*), `e2e_leak.py` | **재현.** 스킴 없는 URL 5건과 `notes.example.co.kr/vault/42`가 남았다 | **재현 안 됨.** 모두 `[REDACTED:URL]`. `https: //…`는 path로 가려진다 | `out/*.probe_mask.txt` |
| GAP-1 | `probe_mask.py` (rrn, secret), `e2e_leak.py` | **재현.** 주민등록번호 3형태와 sk-, Anthropic, ocm_, oc_, AKIA, ghp_, JWT, PEM, xoxb-가 남았다 | **재현 안 됨.** kind `rrn`/`secret`으로 가린다. v.4 목록 밖 잔여: 접두어 없는 AWS secret key, 카드·계좌·여권 번호, 포트·경로 없는 IPv4 | 같은 파일 |
| SAN-* | `probe_redos.py` | 최악 0.008s | 최악 0.040s (12만 자 입력) | `out/*.probe_redos.txt` |
| L1-2 | `l1/f2_hangul_filler.py` (단언을 끈 사본) | **재현** (dce60c1). (a) 채움 문자 40개 rationale ok=True, (b) 채움 문자 라벨 ok=True | **재현 안 됨** (`ba7b438`와 작업 트리 모두). (a) `RATIONALE_MISSING`, (b) `GENERIC_LABEL` + `NOT_NOVEL` | `out/*.f2_hangul_filler_neutral.txt` |
| L1-5 | `l1/f5_near_templated.py` (단언을 끈 사본) | **재현.** T1(라벨 치환 틀), T2(번호만 다름), T3(한 단어만 다름) 모두 ok=True | **부분 재현.** T1은 `TEMPLATED_RATIONALE`(5/5)로 거부된다. T2·T3는 여전히 ok=True다. 근사 중복은 Oracle §10에서 v.5 후보로 연기됐다 | `out/*.f5_near_templated_neutral.txt` |
| L1-7 | `l1/f7_stale_v2_messages.py`, `refuter-l1-7/repro.py`, `repro_host.py` | **재현.** 메시지와 규칙에 v.2 문구("plus the edge's own refs", "∪ 엣지의 출처", "source-to-source emergent")가 출력마다 5회씩 나왔다 | **재현 안 됨.** v.2 문구 0회. 메시지와 규칙은 양 끝 노드 기준을 말한다. 안내를 따른 CTRL은 ok=True, 비창발 복사 엣지 NN은 `NOT_NOVEL`이다. TASK-001 §3은 이미 v2026-10-06.4다(`ba7b438`) | `out/*.f7_*.txt`, `out/*.l17_*.txt` |
| MATCH-2 | `match/p3_auto_misfire.py`, `p4_service_m3.py` | **재현** (dce60c1). p3에서 19개 중 15개가 TOPIC이었다. '내가 만든 두뇌를 평가해줘'는 C를 '만든'으로 붙여 커널을 열었다(0.25). p4의 다른 2건은 `NO_RELEVANT_SUBBRAIN`이었다 | **재현 안 됨.** p3 19/19 whole_host, p4 3/3 whole_host(D 없음) | `out/*.p3_auto_misfire.txt`, `out/*.p4_service_m3.txt` |

참고(파인딩 밖): `match/p9_service_topic.py`의 topic 모드 결과는 이렇다. '기후 변화 대응'이 X를 '대응' 하나로 붙인다(0.2667). 이것은 MATCH-3에 해당하는데, MATCH-3은 확인되지 않은 파인딩이라 이번 범위에 들지 않는다. 수정 전후 결과가 같다.

## 6. TS 사보타주 재실행 결과

방법: judge의 `oracle-mut/mutations.py`에서 TS 파인딩에 묶인 22개 변이를 가져왔다. 20개는 원문 그대로 현재 src에 정확히 1번씩 들어맞았다. T80과 T81은 `_check_templated`가 바뀌어 글자가 맞지 않아서, 같은 뜻으로 옮겼다(`$I/mutations_v4.py`). 변이마다 작업 트리의 rsync 사본을 새로 만들고 변이 1개를 넣은 뒤 `tests/oracle`을 돌렸다. 변이 없는 사본은 604 passed다. §1의 통합 변경을 반영한 최종 트리로 22개를 다시 돌렸고, 결과는 첫 실행과 같았다.

| TS | 변이 | 사보타주 | tests/oracle | 잡은 v4 테스트 |
|---|---|---|---|---|
| TS-1 | T21 | 호스트가 비공개가 된 뒤에도 canal_get이 호스트 내용을 준다 | **빨강** 1 | `test_never_02_v4_host_switched_private_is_withheld_in_canal_get` |
| TS-2 | T05 | stdio에 토큰이 없으면 첫 사용자로 동작 | 사본에서는 초록. **stdio 하위 프로세스가 변이를 실행하게 하니 빨강 5** | `test_never_12_v4_stdio_bad_token_lists_nothing_and_every_call_is_unauthorized[unset/empty/whitespace/bogus/revoked]` (아래 주 1) |
| TS-2 | T90 | `opencanal backup`이 평문 스냅샷을 쓴다 | **빨강** 5 | `test_must_e1_v4_cli_backup_is_encrypted_and_0600`, `..._restore_round_trip`, `..._refuses_existing_target`, `..._refuses_existing_sqlite_sidecar[-wal/-shm]` |
| TS-3 | T12 | 남에게 확인 안 된 최신 버전을 준다 | **빨강** 3 | `test_never_04_v4_unconfirmed_v2_is_invisible_to_others`, `..._publishing_v2_with_v1_hash_is_confirmation_mismatch[2종]` |
| TS-3 | T13 | 아무 버전의 해시로 공개 확인 | **빨강** 2 | `test_never_04_v4_publishing_v2_with_v1_hash_is_confirmation_mismatch[2종]` |
| TS-4 | T15 | 태그를 가리지 않는다 | **빨강** 49 | `test_never_04_v4_value_is_masked_everywhere[*-tag]`, `..._service_import_preview_store_and_published_copy`, `..._invisible_characters_are_removed_on_import` |
| TS-4 | T16 | 엣지 요약을 가리지 않는다 | **빨강** 53 | 같은 묶음(`*-edge_summary`) |
| TS-4 | T17 | 도메인을 가리지 않는다 | **빨강** 25 | `test_never_04_v4_value_is_masked_everywhere[*-domain]` 등 |
| TS-5 | T50 | τ 무시(관련도 > 0이면 선택) | **빨강** 11 | `test_must_m1_v4_below_tau_never_selected_by_match`, `..._canal_open_never_includes_below_tau_even_with_room` 등 |
| TS-6 | T06 | initialize instructions에 Pro/Expert 도구 이름 | **초록 (살아남음)** | 없음 (§7) |
| TS-6 | T07 | Free에게 보내는 합성 프로토콜에 Pro 도구 이름 | **빨강** 1 | `test_never_06_v4_no_free_response_names_a_hidden_tool` |
| TS-6 | T25 | SOURCE_MISMATCH 메시지가 남의 라벨을 인용 | **초록 (살아남음)** | 없음 (§7) |
| TS-6 | T26 | match_explain이 제목을 봉투 밖에 | **빨강** 4 | `test_never_09_v4_member_responses_...[user_b/c/e]`, `test_never_09_v4_host_responses_...` |
| TS-6 | T28 | export 그래프를 봉투 밖에 | **빨강** 4 | 같은 묶음 |
| TS-7 | T66 | 엣지 직접 호스트 출처가 호스트 닿음으로 셈 | **빨강** 1 | `test_must_q3_v3_edge_level_host_ref_does_not_touch_host` |
| TS-7 | T67 | 주인 대신 서브브레인 수로 창발 판정 | **빨강** 2 (+ 오류 15) | `test_must_q3_v4_two_subbrains_of_one_owner_are_not_emergent`, `..._owner_count_not_subbrain_count`. 오류 15건은 `test_oracle_v4_exposure.py`의 NEVER-11 테스트에서 fixture의 실제 통계 자체 점검이 실패한 것이다(변이가 두 세계의 실제 통계를 같게 만든다) |
| TS-8 | T70 | rationale 하한 40 → 20 | **빨강** 6 | `test_must_q4_rationale_length_boundaries[39-False]`, `test_must_q4_v4_invisible_padding_does_not_count[…]` |
| TS-8 | T73 | 새 라벨을 자기가 인용한 노드 라벨과만 비교 | **빨강** 2 | `test_must_q5_v4_new_label_equal_after_normalization_is_not_novel[…]` |
| TS-8 | T74 | 복사 엣지 검사가 방향을 따진다 | **빨강** 3 | `test_must_q5_v3_copied_input_edge_any_direction_is_not_novel[*_reversed]` |
| TS-8 | T79 | 템플릿 한도 20% → 45% | **빨강** 2 | `test_must_q7_three_of_ten_identical_rationales_is_templated`, `test_must_q7_v4_rationales_differing_only_by_endpoint_labels_are_identical` |
| TS-8 | T80 | 묶음마다 추가 복사본만 셈 (이식) | **빨강** 2 | 같은 2개 |
| TS-8 | T81 | 비창발 엣지도 분모에 넣음 (이식) | **초록 (살아남음)** | 없음 (§7) |

주 1 (T05): `test_oracle_v4_transport.py`의 stdio 테스트는 공식 mcp `stdio_client`로 `.venv/bin/opencanal`을 띄운다. 이 클라이언트는 환경 변수를 기본 허용 목록(HOME, LOGNAME, PATH, SHELL, TERM, USER)과 테스트가 준 `OPENCANAL_*`만 넘긴다. 그래서 scratch 사본에서 `PYTHONPATH`를 바꿔도 하위 프로세스는 editable 설치로 실제 저장소의 src를 import한다. 확인 방법: scratch venv(`$I/svenv_T05`)를 만들고, 그 안의 `.pth`가 변이 사본 src를 먼저 가리키게 했다. 그 venv의 python으로 pytest를 돌리면 stdio 테스트 5건이 실패한다(`revoked: import landed on user_a` 등). 같은 방식으로 변이 없는 사본을 돌리면 604 passed다. 실제 저장소에서는 `.venv/bin/opencanal`이 바로 이 저장소의 src를 가리키므로 테스트가 대상 코드를 시험한다.

판정:
- **닫힘**: TS-1, TS-2(T05는 주 1의 방법으로), TS-3, TS-4, TS-5, TS-7.
- **부분 닫힘**: TS-6(T07·T26·T28 닫힘, T06·T25 남음), TS-8(T70·T73·T74·T79·T80 닫힘, T81 남음).
- 살아남은 3개가 실제로 나쁜 동작을 만든다는 것은 judge 프로브로 확인했다(같은 동작을 하는 변이가 아니다). T06: initialize instructions에 `match_explain`, `deltabrain_export`, `canal_synthesize`가 나온다. T25: canal_submit 거부 메시지에 C의 라벨 '형태 상보성'이 봉투 밖에 나온다. T81: 2/9 중복에 비창발 엣지 rationale을 더하면 ACCEPTED된다.

## 7. 남은 실패와 의심되는 테스트

- 남은 실패: **없음** (1285 passed).
- Oracle 문구와 어긋나서 실패하는 Oracle 테스트: **없음**. 실패한 테스트가 없었으므로, 구현을 테스트에 맞춰 굽힌 일도 없다.
- **Oracle 테스트 범위의 빈틈** (테스트 작성자 몫이다. 통합 담당은 `tests/oracle/`을 고치지 않았다):
  1. TS-6 / T06 (NEVER-06): 어떤 oracle 테스트도 MCP `initialize` 결과의 instructions를 보지 않는다. 단위 테스트 2개(`test_unit_mcp.py::test_http_free_tier_never_sees_higher_tier_tools_but_pro_does`, `::test_server_settings`)만 잡는다.
  2. TS-6 / T25 (NEVER-09): `canal_submit`의 `VALIDATION_FAILED` 응답이 NEVER-09 워커를 거치지 않는다. NEVER-06 스윕은 bad-generic 거부를 부르지만 숨긴 도구 이름만 본다. 그리고 SOURCE_MISMATCH가 나는 제출은 없다. 단위 테스트 `test_unit_validator.py::test_source_label_must_match_cited_label`만 잡는다.
  3. TS-8 / T81 (MUST-Q7): 비창발 엣지에 rationale을 붙여 비율을 묽히는 경우를 oracle도 unit도 시험하지 않는다.
- 하네스 주의: 위 주 1과 같다. stdio oracle 테스트는 `PYTHONPATH`가 아니라 venv에 설치된 `opencanal` 콘솔 스크립트를 시험한다. 다른 체크아웃에서 같은 venv로 돌리면 다른 코드를 시험할 수 있다.
- 테스트 작성자가 밝힌 해석상 선택. 실패는 아니고 위험으로 남긴다:
  - CLI 플래그(`backup --out`, `restore --db --in`, `init-db --db --key-file`)와 환경 변수 `OPENCANAL_DB`, `OPENCANAL_KEY_FILE`, `OPENCANAL_CONFIG_DIR`는 계약에 없다. `--help`에서 가져왔다.
  - restore 거부는 0이 아닌 종료 코드로 고정했다. Oracle은 "거부"라고만 한다. -wal/-shm 거부는 MUST-E1 "같은 데이터를 되살린다"에서 끌어냈다.
  - 확인 안 된 v2를 남이 `version=2`로 부르면, v1 대체 응답과 NOT_FOUND 둘 다 허용한다. 대신 `version=99`와 바이트가 같아야 한다.
  - NEVER-04: 이메일 도메인이나 전화번호 끝자리만 남기는 부분 마스킹은 통과한다(고유 탐침만 본다). 저장 텍스트의 NFKC 여부는 고정하지 않았다. 노드 ID를 가렸을 때 그 노드를 가리키던 엣지가 남는지는 고정하지 않았다.
  - NEVER-11 비교는 deltabrain_get·list·rate·export만 본다. canal_get은 전환 전부터 참여자가 멤버 신원을 봤으므로 넣지 않았다.
  - TS-7: owners_involved를 서로 다른 주인 수로 읽었다.

## 8. 연기한 항목 (v.5 후보, 이번 라운드에서 고치지 않음)

| 항목 | 상태 |
|---|---|
| L1-4 내용 없는 rationale | Oracle §10. 고치지 않았다 |
| L1-5 나머지 (근사 중복) | Oracle §10. f5 T2·T3는 여전히 통과한다(§5) |
| L1-6 라벨 재조합·일반어 회피 | Oracle §10 |
| MATCH-4 조사 과잉 제거, MATCH-5 겹조사·어미 | Oracle §10. matching.py는 바뀌지 않았다 |
| EXP-6 기여자 연결(서브브레인 ID), 토큰 길이 | Oracle §10 |
| DB 파일 권한 0600 (MUST-E3 제안) | Oracle §10. 새로 만드는 DB는 여전히 umask를 따른다. restore로 만든 DB만 0600이다 |
| MUST-E2 확대 제안 | "평문 토큰은 로그에도 남지 않는다". TIER-2 수정은 했지만 Oracle 기준은 아직 저장소만 말한다 |
| SAN 잔여 (v.4 목록 밖) | 난독화 이메일(`kim[at]…`, `kim @ …`, `"kim lee"@…`, `kim@[IP]`), 키릴 문자 닮은꼴 경로, 상대 경로(`../kim/…`, `Users/kim/…`, `~kim`), `/data`·`/workspace`, 카드·계좌·여권 번호, 포트·경로 없는 IPv4, 접두어 없는 AWS secret key, 한글로 쓴 숫자, 아랍-인도 숫자, `010/1234/5678`·`010_1234_5678` 같은 드문 구분자 |

## 9. 남은 위험

- **오너 확인이 필요한 계약·문서 변경** (통합 담당 소유가 아니다):
  - TASK-001 §4 시그니처 추가: `Store.create_canal(..., *, canals_per_month=None)`, `Store.set_visibility(..., *, max_public=None)`. 키워드 전용이고 기본값이 있어 기존 호출은 그대로 동작한다.
  - TASK-001 §5 envelope 변경:
    - deltabrain_get: `ratings`를 `untrusted_data.ratings`로 옮겼다. 최상위 `stats`는 숫자만 남고, 최상위 `rating_summary`가 새로 생겼다. TASK §5 표는 아직 "`ratings` 요약"이라고 적고 있다.
    - deltabrain_rate: `edge_id`를 `untrusted_data`로 옮겼다.
    - canal_open·canal_get `members[]`: `owner_display`를 뺐다.
    - canal_get: `matched_terms`를 `untrusted_data.subbrains[]`로 옮겼다. withheld 행은 ID만 남는다.
    - canal_open `members[].matched_terms`는 최상위에 남겼다. 기존 oracle 테스트가 그 위치를 읽고, 값은 호출자 자신의 질의나 호스트에서 나온다. 단, NEVER-09 v.4는 "매칭 용어"를 남이 쓴 문자열로 꼽는다. 호스트 본인에게만 가는 응답이라 위반은 아니라고 SS 빌더가 판단했다. 오너 확인이 필요하다.
  - `PROTOCOL_VERSION`을 올리지 않았다. 고정 파일 `models.py`에 있기 때문이다. canal_open이 보내는 규칙·지시 문구는 바뀌었는데 버전 표기는 그대로다.
  - HUMAN-01: 가려진 기여자를 보는 참여자는 저장된 통계로는 비창발인 엣지를 평가할 수 있다. 평가는 저장되지만, 실제 통계로 계산하는 품질에서는 빠진다.
  - CRY-1 E 경우: 새 경로로 복원한 뒤 옛 경로로 `mv`하면 옛 -wal/-shm이 다시 적용된다. README 운영 절차("서버를 멈추고 -wal/-shm을 DB와 함께 옮긴다")에 한 줄이 필요하다.
- **이번 통합 변경의 부작용**: 앞 숫자가 대표번호 접두(1522·1533·…·1600·1611·…·1800·…·1899)인 연도 범위는 바로 뒤에 `년`/`年`이 없으면 `[REDACTED:PHONE]`이 된다. `1600-1700`, `1800-1900`이 그렇고, 영문 표기(`1800-1900s`, `1800-1900 AD`)도 연도 표시로 보지 않아 가려진다. 일부러 과하게 가리는 쪽을 택했다. 글자 수 제한으로 잘려 `년`이 떨어져 나가도 가려진다.
- **SAN 빌더가 보고한 부작용**: 저장 텍스트에 NFKC를 적용하므로 ㎡ → m2, ① → 1, ㈜ → (주), … → ...로 바뀐다. 구분자 없는 13자리 숫자 중 날짜 모양이 맞는 것(EAN-13 바코드, 밀리초 타임스탬프)은 주민등록번호로 가려진다. `e-/etc`, `Plan A:/B`는 경로로 가려진다.
- **SS 빌더 설계**: 보는 사람이 호스트 출처를 가려진 형태로 보면, 그 엣지는 호스트에 닿는다고 세지 않는다. `_write_txn`의 BEGIN IMMEDIATE가 busy timeout(5s)을 넘기면 `INTERNAL`로 끝난다(fail closed). 하드 링크가 없는 파일 시스템에서는 restore가 다시 확인한 뒤 rename으로 넘어간다. 확인과 rename 사이에 아주 짧은 틈이 남는다.
- **CLI 빌더 설계**: `serve`는 SIGTERM에 종료 코드 143을 낸다(예전에는 시그널로 죽었다). `mcp-stdio`의 SIGTERM 경로는 손대지 않았다. 로그의 토큰 모양 규칙에는 왼쪽 경계가 없어서 `doc_identifier` 같은 낱말도 `doc_ide…`로 잘린다. 보기에만 영향이 있다.
- **TS 빈틈**: §7의 3개 사보타주(T06, T25, T81)는 oracle 테스트로 막혀 있지 않다. T81은 단위 테스트로도 막혀 있지 않다.
- **모듈 크기**: 시작 상한 약 600줄을 넘는다. store.py 964줄, service.py 848줄, validator.py 713줄, cli.py 662줄, sanitize.py 652줄이다.
- **rollback**: 이번 라운드에 스키마 변경은 없다. 되돌리려면 `ba7b438` 대비 작업 트리 변경(src 8개 파일, unit 테스트, 새 oracle 테스트 파일)을 버린다. SS 빌더가 원본 `store.py.orig`, `service.py.orig`를 scratchpad에 남겼다.
