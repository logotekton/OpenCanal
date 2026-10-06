# TASK-001 — opencanal v0 얇은 조각: 서브브레인 → 커널 → 델타브레인, 로컬 MCP

> NDSH 부록 B-3 양식. 이 문서가 Builder에게 주는 허용 범위와 인터페이스 계약이다.

## 1. 목적과 현재 재현

- **Risk ID:** RISK-001 (F1~F12)
- **사용자 결과:** 사용자의 LLM이 로컬 MCP로 아래 흐름을 끝까지 수행한다. 서브브레인 가져오기 → 미리보기 확인 후 공개 → 질의로 커널 열기 → 다른 사람 서브브레인을 받아 합성 → 델타브레인 제출(L1 검증) → 참여자 전원이 조회 → 창발 엣지에 L2 라벨
- **현재 상태:** 계약 코드(`models.py`, `textnorm.py`, `config.py`)와 스텁만 있다. 다른 모듈은 `NotImplementedError`를 던진다.

## 2. 범위

- **수정 가능:**
  - `src/opencanal/` 아래 스텁 모듈: `sanitize`, `validator`, `matching`, `crypto`, `store`, `protocol`, `service`, `mcp_server`, `app`, `cli`, `__main__`
  - `tests/unit/`(Builder 자체 테스트)
  - `README.md`의 "실행" 절
- **수정 금지:** `docs/oracle/`, `config/`, `fixtures/`, `tests/oracle/`, `src/opencanal/models.py`, `textnorm.py`, `config.py`, 그리고 `docs/`의 나머지 문서
- **새 의존성:** `pyproject.toml`에 있는 것(`mcp`, `fastapi`, `uvicorn`, `pydantic`, `cryptography`, `pytest`, `httpx`)만 쓴다. 추가하려면 보고한다
- **DB/권한/CI 변경:** 새 SQLite 스키마. migration 없음 (새 DB). CI 없음 (R0)
- **변경량 시작 상한:** 모듈당 약 600줄. 넘으면 이유를 남긴다

## 3. 기준

- **수용 기준 ID:** MUST-Q0~Q9, MUST-M1·M3·M4, PROV-M2(잠정), MUST-T1, MUST-C1·C2, MUST-E1·E2
- **금지 동작 ID:** NEVER-01~12
- 정본: `docs/oracle/ORACLE_MANIFEST.md` v2026-10-06.2

## 4. 모듈 소유와 계약

모든 public 시그니처는 스텁에 있다. 시그니처를 바꾸지 않는다. 바꿔야 하면 보고한다.

| Builder | 파일 | 핵심 계약 |
|---|---|---|
| S | `sanitize.py` | `import_document()`, `content_hash()` — 허용 필드만 남기고, 경로·이메일·전화·URL을 가리고, 가린 내역을 `Redaction`으로 남긴다. OpenCrab 형식(`nodes[].node_type/properties`, `edges[].from_id/to_id`)을 지원한다 |
| V | `validator.py` | `validate_deltabrain()` — ORACLE §4·§5.1을 그대로 구현한다. 모든 위반을 한 번에 돌려준다. 순수 함수 |
| M | `matching.py` | `match()` 외 — ORACLE §5.4, `config/matching.json` 공식(스텁 docstring). 결정적 |
| K | `crypto.py` | 토큰 해시, 마스터 키(0600), AES-SIV 기여자 토큰(HKDF 서브키), Fernet 백업 |
| ST | `store.py` | SQLite. viewer 범위 접근자만 도구에 노출한다. NOT_FOUND로 존재를 숨긴다. 비공개 기여자 마스킹(`get_deltabrain_for_viewer`). 감사 로그 |
| SV | `service.py`, `protocol.py` | `tools_for`, `dispatch`, 도구 핸들러 전부(아래 §5), 합성 프로토콜 |
| MCP | `mcp_server.py`, `app.py`, `cli.py`, `__main__.py` | FastMCP 서브클래스(`list_tools`/`call_tool` 재정의 → Service), `/mcp/{token}` streamable HTTP(stateless), stdio(`OPENCANAL_TOKEN`), CLI |

## 5. 도구 계약 (`Service.dispatch`)

모든 응답은 envelope다. 성공은 `{"ok": true, ...}`, 실패는 `{"ok": false, "error": {"code", "message", ...}}`이다. 다른 사용자의 내용은 `untrusted_data` 아래에 둔다.

| 도구 | 인자 | 성공 응답 핵심 | 실패 코드 |
|---|---|---|---|
| `subbrain_import` | `document`(obj), `format?`("canonical"\|"opencrab"), `title?`, `domains?`, `subbrain_id?` | `subbrain_id`, `version`, `visibility:"private"`, `content_hash`, `redactions[]`, `preview{title,domains,node_count,edge_count,nodes[:20]}` | IMPORT_INVALID, NOT_FOUND |
| `subbrain_list_mine` | — | `subbrains[]` (SubbrainSummary) | — |
| `subbrain_get` | `subbrain_id`, `version?` | 내 것이면 그대로, 남의 것이면 `untrusted_data.subbrain` | NOT_FOUND |
| `subbrain_set_visibility` | `subbrain_id`, `visibility`("public"\|"private"), `version?`, `confirm_hash?` | SubbrainSummary | CONFIRMATION_MISMATCH, LIMIT_EXCEEDED(공개 수), NOT_FOUND |
| `subbrain_search` | `query`, `limit?`(≤20) | `untrusted_data.results[]` {subbrain_id, version, title, domains, owner_display, relevance, matched_terms} — 공개만, relevance ≥ τ만 | — |
| `canal_open` | `query`, `host_subbrain_id`, `query_mode?` | `canal_id`, `query_mode_used`, `members[]`(점수), `truncated`, `protocol`, `untrusted_data{notice, host, subbrains[]}` | HOST_NOT_PUBLIC, NOT_FOUND, NO_RELEVANT_SUBBRAIN(커널 미생성·미차감), LIMIT_EXCEEDED(월 커널) |
| `canal_get` | `canal_id` | 커널 + 지금 공개인 멤버 내용 (`untrusted_data`). 비공개로 바뀐 멤버는 `withheld:true`, 내용 없음 | NOT_FOUND |
| `canal_submit` | `canal_id`, `deltabrain`(obj) | `deltabrain_id`, `stats` | NOT_CANAL_HOST, HOST_NOT_PUBLIC, VALIDATION_FAILED(`violations[]`), NOT_FOUND |
| `deltabrain_get` | `deltabrain_id` | `untrusted_data.deltabrain` (store 마스킹 적용), `ratings` 요약 | NOT_FOUND |
| `deltabrain_list` | — | `deltabrains[]` 요약 | — |
| `deltabrain_rate` | `deltabrain_id`, `edge_id`, `novelty`, `validity`, `usefulness` (0/1) | `ok` | NOT_FOUND, NOT_EMERGENT_EDGE, INVALID_ARGUMENT |
| `match_explain` (Pro+) | `query`, `host_subbrain_id`, `query_mode?` | MatchResult 전체(τ 미만 포함), 커널 생성·차감 없음 | HOST_NOT_PUBLIC 아님 — 호스트는 내 서브브레인이면 공개 여부 무관, NOT_FOUND |
| `deltabrain_export` (Pro+) | `deltabrain_id` | `untrusted_data.graph` {nodes, edges} JSON | NOT_FOUND |
| `canal_synthesize` (Expert) | — | — | 항상 NOT_AVAILABLE |

규칙:

- `dispatch` 순서: 인증 → 도구 존재 → 티어 → 인자 검증 → 핸들러. 앞 단계에서 실패하면 부작용이 없다.
- 커널당 멤버 수는 `limits.max_members_per_canal`로 match에 전달한다. 잘리면 `truncated: true`.
- 월 커널 수는 커널을 **만든 경우만** 센다 (UTC 월).
- 공개 서브브레인 수 상한은 public 전환 때 검사한다 (이미 공개인 것을 다시 공개하는 경우는 세지 않는다).
- `canal_submit`: 호스트만 제출한다. 호스트 서브브레인이 아직 공개인지 다시 확인한다. 검증 컨텍스트는 서버가 `store.canal_context()`로 만든다.
- 비공개로 바뀐 멤버를 인용한 새 제출은 `PROVENANCE_OUT_OF_CANAL`이다 (컨텍스트에서 빠지므로).

## 6. 검증

- **자동 검사:** `.venv/bin/python -m pytest -q` — `tests/oracle/`(독립 작성)와 `tests/unit/` 모두 초록
- **빨강 → 초록 기록:** 통합 전 실패 수와 통합 후 결과를 `evidence/CHANGE-001.md`에 남긴다
- **사람 여정:** `opencanal seed-fixtures` → `opencanal serve` → Claude Code에 `http://127.0.0.1:8765/mcp/<token>` 등록 → Q-01 흐름을 손으로 실행
- **실패 주입:** 잘못된 토큰, 남의 ID 직접 호출, 공격 서브브레인 X, 상위 티어 도구 직접 호출
- **운영 신호:** 감사 로그(`audit` 테이블)에 공개·비공개 전환, 커널 생성, 제출 거부·수락이 남는다

## 7. Migration Plan

미적용 — 새 DB다.

## 8. 완료

- diff 설명, 실행 명령과 결과는 `evidence/CHANGE-001.md`에 남긴다
- **남은 위험:** TASK-002(보관 기간·영구 삭제·고지), 매칭 기준(오너 미결), L2 라벨러 1명
- **rollback·데이터 복구:** v0 DB는 `seed-fixtures`로 다시 만든다. 또는 `opencanal restore`

## 9. 다음 작업 (이 TASK 범위 밖)

- TASK-002: 보관 기간, 운영자용 영구 삭제 경로, 복원 후 재삭제, 고지 (D-005)
- 매칭 기준 연구: `match_explain` 결과를 오너가 검토한 뒤 결정 (D-003)
