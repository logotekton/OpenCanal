# CHANGE-001 — TASK-001 통합 기록 (opencanal v0)

> NDSH 부록 B-7 양식. 통합 담당(Integrator)이 2026-10-06에 남긴 기록이다. 사실만 적는다.
> 기준: `docs/oracle/ORACLE_MANIFEST.md` v2026-10-06.2, `tasks/TASK-001.md`.

## 1. 변경 요약

빌더 7명(S, V, M, K, ST, SV, MCP)이 각 모듈을 구현하고, 테스트 작성자가 `fixtures/`와 `tests/oracle/`을 독립적으로 썼다. 통합 단계에서 바꾼 것은 아래뿐이다.

| 파일 | 변경 |
|---|---|
| `src/opencanal/service.py` | `Service(..., clock=...)`로 시계를 넘기면 `store.clock`도 같은 시계로 맞춘다 (월 커널 수 계산 불일치 수정) |
| `src/opencanal/mcp_server.py` | `call_tool` 예외 대비 envelope의 코드를 `"INTERNAL_ERROR"` 대신 `service.INTERNAL_CODE`(`"INTERNAL"`)와 `INTERNAL_MESSAGE`로 바꿨다 (계층 사이 코드 통일) |
| `tests/unit/test_unit_mcp.py` | 위 변경에 맞춰 단언 1개를 `{"code": "INTERNAL", "message": "internal error"}`로 고쳤다 |
| `tests/unit/test_unit_integration.py` (신규) | 실제 Store·crypto·sanitize·matching과 config로 주입한 시계(2031-01)가 월 커널 한도에 반영되는지 확인한다. 시계를 넘기지 않으면 `store.clock`을 건드리지 않는지도 확인한다 |
| `evidence/CHANGE-001.md` (신규) | 이 문서 |

고정 파일(`docs/`, `config/`, `fixtures/`, `tests/oracle/`, `models.py`, `textnorm.py`, `config.py`, `pyproject.toml`)은 건드리지 않았다. 커밋하지 않았다.

## 2. 실행 명령

```bash
# 자동 검사 (저장소 루트)
.venv/bin/python -m pytest -q -p no:cacheprovider            # 전체
.venv/bin/python -m pytest -q -p no:cacheprovider tests/oracle
.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit

# 수동 여정 (스크래치 디렉터리, 저장소 data/는 쓰지 않음)
export OPENCANAL_DB=$SP/data/opencanal.db OPENCANAL_KEY_FILE=$SP/data/keys/master.key
.venv/bin/opencanal init-db
.venv/bin/opencanal seed-fixtures
.venv/bin/opencanal match-explain --token <user_a 토큰> --query "모듈러 건축의 현장 조립 오류를 줄일 아이디어" --host-subbrain-id <A의 subbrain_id>
.venv/bin/opencanal create-user --name "Pro Tester" --tier pro --user-id user_pro
.venv/bin/opencanal set-tier --user-id user_a --tier pro      # 확인 후 free로 되돌림
.venv/bin/opencanal serve --port <빈 포트>                   # /health, 공식 mcp 클라이언트로 list_tools·call_tool
.venv/bin/opencanal backup --out $SP/bk
.venv/bin/opencanal restore --in $SP/bk/<파일>.db.enc --db $SP/restored.db
```

## 3. 빨강 기준선 (통합 전)

- 명령: `.venv/bin/python -m pytest -q -p no:cacheprovider`
- 결과: **515 passed, 0 failed, 0 errors** (4.04s). 이 중 oracle 161개, unit 354개다.
- 대표 실패: 없음. 통합을 시작할 때 모든 모듈이 이미 구현되어 있었기 때문이다. TASK가 기대한 "대부분 NotImplementedError로 실패하는 빨강"은 재현되지 않았다.
- 이 테스트들이 실패할 수 있다는 근거:
  - 테스트 작성자의 보고: 메모리 안에서 구현을 일부러 망가뜨리자 oracle 테스트가 실패했다. validator가 항상 ok를 돌려주면 37건, 상위 티어 도구를 노출하면 5건, untrusted_data 밖으로 노출하면 2건 등이다. 이 실험은 통합 담당이 다시 돌리지 않았다.
  - 통합 담당이 직접 확인한 것: 새 통합 테스트 `test_injected_service_clock_drives_store_month_for_monthly_canal_limit`를 수정 전 상태로 돌렸다. 스크래치 pytest 플러그인이 `Service.__init__` 뒤에 `store.clock`을 벽시계로 되돌리는 방식이다. 결과는 **1 failed**였다. `created_at`이 `'2026-10-06T08:40:14+00:00'`라서 `'2031-01'`로 시작하지 않았다.

## 4. 초록 결과 (통합 후)

- 전체: **517 passed** (4.32s). 실패와 오류는 없다.
- `tests/oracle`: **161 passed**
- `tests/unit`: **356 passed** (기존 354개 + 신규 통합 테스트 2개)

## 5. 고친 통합 버그

1. **월 커널 수에서 서비스 시계와 저장소 시계가 어긋남**
   - 증상: `Service`는 주입된 시계로 `"YYYY-MM"`을 만든다. 반면 `Store.count_canals_in_month`는 Store가 자기 시계로 찍은 `canals.created_at`을 센다. 시계를 주입하면(예: 2031-01) 센 값이 항상 0이 되어, 월 커널 한도(`LIMIT_EXCEEDED`, MUST-T1)가 걸리지 않는다.
   - 원인: ST와 SV 빌더가 둘 다 이 문제를 보고했지만, 연결하는 코드가 없었다.
   - 수정: `Service.__init__`에서 `clock`이 주어졌을 때만 `store.clock = clock`을 넣는다.
   - 확인: 신규 통합 테스트로 수정 전 실패, 수정 후 통과를 봤다. 관련 단위 테스트 `test_canal_open_monthly_limit_uses_clock_month`와 `test_count_canals_in_month_uses_clock`도 통과한다.
   - 영향 범위: oracle 테스트는 시계를 주입하지 않으므로(`tests/oracle`에 `clock` 없음) 결과가 바뀌지 않는다.
2. **내부 오류 코드가 계층마다 다름**
   - `Service.dispatch`는 `"INTERNAL"`, MCP 전송 계층의 예외 대비 경로는 `"INTERNAL_ERROR"`를 썼다.
   - 수정: `mcp_server.py`가 `service.INTERNAL_CODE`와 `INTERNAL_MESSAGE`를 가져다 쓴다.
   - 남은 점: 두 코드 모두 `models.ErrorCode`에는 없다. `models.py`는 고정 파일이라 TASK 갱신이 필요하다 (§8).

## 6. 남은 실패와 의심되는 테스트 이슈

- 남은 실패: **없음**.
- 의심되는 테스트 이슈: **없음**. 통합 후 실패한 oracle 테스트가 없다. 테스트를 통과시키려고 구현을 굽히거나 고정 파일을 고친 일도 없다.
- 참고로, 테스트 작성자가 스스로 밝힌 해석상 선택이 있다. 실패는 아니며 아래 위험으로 남긴다.
  - NOT_FOUND 비교는 envelope 전체를 본다. 메시지에 요청 ID나 시각을 넣으면 깨진다.
  - D-005("삭제"/"철회" 금지어)를 NEVER-03보다 엄격하게 고정했다.
  - Q-01의 A2 포함(0.56)을 고정했다.

## 7. 수동 여정 결과

스크래치 디렉터리에서 실행했다(`OPENCANAL_DB`, `OPENCANAL_KEY_FILE` 지정). 토큰은 출력에서만 확인했고 이 문서에는 적지 않는다.

| 단계 | 결과 |
|---|---|
| `init-db` | rc=0. DB를 만들었다. 키 파일은 `-rw-------`(0600), 키 디렉터리는 `drwx------` |
| `seed-fixtures` | rc=0. A·A2·B·C·D·X는 `imported + published`, P(user_b)는 `imported`(private). redactions는 모두 0. 사용자 6명(user_a/b/c/d/e/x)의 토큰과 MCP URL을 한 번만 출력했다 |
| `match-explain` (user_a, free) | `TIER_FORBIDDEN`, rc=1. 의도대로다 (NEVER-07) |
| `match-explain` (새 pro 사용자 user_pro, host = A의 subbrain_id) | `NOT_FOUND`, rc=1. **의도대로다.** TASK §5에서 `match_explain`의 호스트는 "내 서브브레인"이어야 한다. 남의 공개 서브브레인을 호스트로 주면 존재하지 않는 ID와 같은 `NOT_FOUND`다 (NEVER-01, 존재 노출 금지) |
| `match-explain` (가짜 토큰) | `UNAUTHORIZED`, rc=1 (NEVER-12) |
| `match-explain` (user_a를 `set-tier pro`로 올린 뒤, Q-01) | topic 모드. 용어는 [모듈러, 건축, 현장, 조립, 오류]. 선택: A2 0.56, B 0.40, C 0.40. τ 미만: D 0.00, X 0.00. A(호스트)와 P(비공개)는 후보에 없다. 전략은 relevance_plus_diversity, max_members는 6 |
| 같은 조건, Q-02 "내 두뇌를 평가해줘" | `query_mode_used: whole_host`. 용어는 A의 태그와 라벨이다("두뇌"와 "평가"는 없음). 선택: A2 1.00, C 0.45, B 0.40. D는 0.00, below_tau |
| 같은 조건, Q-03 "제빵 반죽 발효 온도" | 모든 후보가 0.00, below_tau. 선택 없음. 확인 후 user_a를 free로 되돌렸다 |
| `serve` + `GET /health` | `{"ok":true}` |
| 공식 mcp 클라이언트(`streamable_http_client`)로 `list_tools` | free(user_a)는 11개, pro(user_pro)는 13개(match_explain, deltabrain_export 추가), 가짜 토큰은 `[]` |
| 공식 클라이언트로 `call_tool` | free의 match_explain은 `TIER_FORBIDDEN`, pro의 subbrain_list_mine은 ok, 가짜 토큰은 `UNAUTHORIZED`. 매 결과의 TextContent는 1개다 |
| HTTP로 Q-01 흐름 | `canal_open`(user_a)은 ok: topic, 멤버 A2·B·C, truncated=false. 이어서 `canal_submit good-01`(실제 ID로 치환)은 ok: 노드 9, 엣지 10, new 2, owners 3, 창발 8. `deltabrain_get`은 user_b/c/e 모두 ok. 비참여자 user_d와 user_x는 `deltabrain_get`, `canal_get` 모두 `NOT_FOUND`. 멤버 user_b의 `canal_submit`은 `NOT_CANAL_HOST`. Q-03 `canal_open`은 `NO_RELEVANT_SUBBRAIN` |
| 실패 주입 (X, 비공개 P) | `subbrain_search "보안 체크리스트 점검"`은 결과가 X 하나다. `subbrain_get X`에서 주입 문구는 `untrusted_data` 안에만 있고 밖에는 없다. 비공개 P의 `subbrain_get`과 없는 ID의 응답이 완전히 같다(`NOT_FOUND`) |
| 서버 로그 | 전체 토큰은 0회 나타났다. 접근 로그에는 `/mcp/oc_xxx…` 형태로 앞 6자만 남는다 |
| 감사 로그 (`audit` 뷰) | 항목별 건수: user.create 7, subbrain.import 7, subbrain.visibility 6, user.tier 2, canal.open 1, deltabrain.submit 1. 이번 여정에서 제출 거부(`deltabrain.reject`)는 일어나지 않았다(user_b 제출은 검증 전에 NOT_CANAL_HOST로 끝남). 거부 감사는 단위 테스트가 다룬다 |
| 토큰 저장 | `api_tokens` 7행, `token_hash` 길이 64(sha256 hex) |
| `backup` | rc=0. `.db.enc` 파일 권한은 0600. 파일에서 `모듈러`, `Haram Kim`, `SQLite format`이 각각 0회 나왔다. 대조군인 원본 DB에서는 `모듈러`가 4회 나왔다 (MUST-E1) |
| `restore` | 새 경로로 복원 rc=0, 파일 권한 0600. users/subbrains/subbrain_versions/api_tokens/audit_log 행 수가 원본과 같다(7/7/7/7/22). 기존 파일로 복원하면 거부(rc=1), 키 파일이 없으면 거부(rc=1), 다른 키를 쓰면 복호화 실패로 거부하고 파일을 만들지 않는다(rc=1) |
| 서버 종료 | 두 번 띄운 서버를 모두 멈췄다 |

Claude Code에 MCP URL을 등록해 사람이 손으로 하는 Q-01 합성(TASK §6 "사람 여정")은 하지 않았다. 위 HTTP 흐름은 good-01을 그대로 제출한 것이다. LLM 합성으로 대신한 것이 아니다.

## 8. 남은 위험

- **이번 수정의 부작용:** 시계를 넘기면 `Service.__init__`이 받은 Store의 `clock`을 바꾼다. Store 하나를 서로 다른 시계를 가진 Service 두 개가 함께 쓰면, 나중에 만든 Service의 시계가 이긴다. v0의 CLI와 앱은 Service를 하나만 만들므로 지금은 해당하지 않는다.
- **오류 코드 계약:** `INTERNAL`은 `models.ErrorCode`에 없다. 고정 파일이라 바꾸지 않았다. 어느 계층에서든 내부 오류가 나면 계약에 없는 코드가 나간다. TASK 갱신으로 추가할지 정해야 한다.
- **DB 파일 권한:** DB 파일 권한이 0644다(키 파일만 0600). DB에는 비공개 서브브레인 평문과 토큰 해시가 있다. `data/`는 gitignore 대상이지만, 같은 컴퓨터의 다른 계정은 읽을 수 있다. Oracle은 키 파일 권한만 요구한다.
- **match_explain의 owner_id 노출 (Pro 이상):** 후보마다 `owner_id`(내부 사용자 ID)를 최상위에 돌려준다. 공개 서브브레인의 주인이라 Oracle 위반은 아니다. 다만 다른 응답(subbrain_get, canal_open)은 owner_id를 빼므로 일관되지 않다.
- **owner_display 위치:** `canal_open`의 `members[].owner_display`는 `untrusted_data` 밖에 있다. v0에서는 표시 이름을 운영자가 CLI나 fixture로 정한다. 사용자가 직접 정하게 되면 NEVER-09 관점에서 다시 봐야 한다.
- **매칭 기준 미결 (D-003, PROV-M2):** 고정 공식에 따르면 Q-01에 A2(0.56)가 들어간다. 오너 self-test #2의 답은 "잘 모르겠다"였다. 커널링 대상을 고르는 기준은 오너가 `match_explain` 결과를 보고 정한다. whole_host 모드에서는 분모가 5로 막혀, 정확히 일치하는 태그 1개(0.2)만으로 τ에 닿는다.
- **L1 검증기의 빈틈 (V 빌더 보고):** `generic_terms.txt`에 없는 활용형이 있다. 예를 들어 "혁신적인 시너지", "융합을 통한 혁신"은 GENERIC_LABEL을 통과한다. 엣지에 남의 출처를 붙이기만 해도 창발 엣지가 될 수 있다. L2(HUMAN-01)에서만 걸러진다. config는 Oracle 소유라 손대지 않았다.
- **L2 사람 라벨:** HUMAN-01~03은 자동 검사가 없다. 라벨러는 오너 1명이다.
- **기여자 토큰 길이 (K 빌더 보고):** AES-SIV 토큰 길이로 `len(owner_id)`가 드러난다. 그래서 델타브레인 사이 연결을 추측할 여지가 있다. 패딩하면 막을 수 있지만 토큰 형식이 바뀐다.
- **TASK-002 범위 (미구현):** 보관 기간, 법적 요청과 탈퇴 때 쓸 운영자용 영구 삭제 경로, 복원 뒤 다시 삭제, 화면 문구와 약관의 고지("공개/비공개", 서버 보관)가 해당한다. 출시 전에 개인정보보호법 관점의 전문가 확인이 필요하다.
- **테스트 해석에 의존:** NOT_FOUND 동일성 테스트는 메시지까지 비교한다. 오류 메시지에 요청 ID나 시각을 넣으면 Oracle과 무관한 이유로 깨진다. 월 커널 테스트는 실제 UTC 월을 쓰므로, 월 경계에서 돌리면 드물게 흔들릴 수 있다.
- **모듈 크기:** 시작 상한 약 600줄을 넘는다. service.py 811줄, store.py 795줄, validator.py 665줄이다. 이유는 각 빌더 보고에 있다.
- **MCP 결과 표시:** `tools/call` 결과는 `ok:false` envelope이어도 `isError=false`다. 계약("TextContent 정확히 1개")을 글자 그대로 따랐다.
- **HTTP 무토큰:** 토큰 없이 `/mcp`나 `/mcp/`로 오면 307이나 404로 MCP에 닿지 않는다. 이 경우의 HTTP 형태는 계약에 정해져 있지 않다. Service 수준의 fail-closed는 테스트가 다룬다.
- **rollback:** v0 DB는 `seed-fixtures`로 다시 만들거나 `opencanal restore`로 되살린다. 이번 변경에는 스키마 변경이 없다.
