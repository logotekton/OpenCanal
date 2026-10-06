# opencanal — 오픈커널

> **OpenCanAI** · 서로 다른 secondbrain을 이어서, 내 두뇌만으로는 나오지 않는 생각을 창발시킨다.

개인 secondbrain은 내가 모은 데이터를 내가 만든 하네스로 평가한다. 그래서 시간이 지나면 '나'로 오염된다.
opencanal에서는 사용자가 두뇌의 일부(**서브브레인**)를 공개해 둔다. 누군가 질의를 던지면 관련 있으면서도 그 사람과는 **먼** 서브브레인들이 붙어 하나의 **커널**이 열린다. 이 커널링의 결과는 대화 로그가 아니라 지식그래프(**델타브레인**)로 남는다.

사용자의 LLM은 MCP로 플랫폼과 통신한다. 웹사이트는 나중에 만든다.

## 상태

v0 설계 단계 (R0 · 로컬 · 합성 데이터). 코드는 아직 없다.

## 문서

| 문서 | 내용 |
|---|---|
| [START.md](START.md) | 한 장짜리 시작 문서: 문제, 범위, 위험 판정 |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 용어 |
| [docs/PROJECT.md](docs/PROJECT.md) | 사용자 장면, 성공 기준, 핵심 설계 명제 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 스택, 스키마, MCP 도구·티어 계획, 설계 질문 |
| [docs/DATA_MAP.md](docs/DATA_MAP.md) | 데이터 흐름과 신뢰 경계 |
| [docs/risks/RISK-001.md](docs/risks/RISK-001.md) | 기준 위험과 통제 |

개발 절차는 OpenCrab 팩 「비개발자를 위한 개발의 정석」(NDSH)을 따른다.

## 이전 버전

이 레포의 이전 구현(Verified Agent Network, TypeScript 모노레포)은 태그 `archive/agent-network-2026-07`에 남아 있다.

## 실행

v0는 로컬 전용이다(R0). 서버는 `127.0.0.1`에만 띄우고, 합성 두뇌 fixture와 오너 본인 데이터만 쓴다.

### 설치와 준비

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/opencanal init-db          # data/opencanal.db, data/keys/master.key (0600). 새로 만드는 데이터 디렉터리는 0700
.venv/bin/opencanal seed-fixtures    # fixtures/brains/*.json → 사용자·서브브레인, 새 사용자 토큰을 한 번 출력
```

경로는 옵션이나 환경변수로 바꾼다. 상대 경로 기본값은 레포 루트 기준이다.

| 옵션 | 환경변수 | 기본값 |
|---|---|---|
| `--db` | `OPENCANAL_DB` | `data/opencanal.db` |
| `--key-file` | `OPENCANAL_KEY_FILE` | `data/keys/master.key` (`OPENCANAL_MASTER_KEY`가 있으면 그 값을 쓴다) |
| `--config-dir` | `OPENCANAL_CONFIG_DIR` | `config/` |

### 사용자와 토큰

```bash
.venv/bin/opencanal create-user --name "홍길동" --tier free [--user-id user_h]
.venv/bin/opencanal rotate-token --user-id user_h     # 기존 토큰을 모두 폐기하고 새로 발급
.venv/bin/opencanal set-tier --user-id user_h --tier pro
```

토큰과 MCP URL(`http://127.0.0.1:8765/mcp/<token>`)은 만들 때 한 번만 출력된다. 서버에는 토큰 해시만 남는다.
잃어버리면 `rotate-token`으로 다시 발급한다.

### MCP 서버

HTTP(streamable HTTP, stateless):

```bash
.venv/bin/opencanal serve            # --host 127.0.0.1 --port 8765
claude mcp add --transport http opencanal http://127.0.0.1:8765/mcp/<token>
```

stdio:

```bash
claude mcp add opencanal -e OPENCANAL_TOKEN=<token> -- /절대경로/opencanal/.venv/bin/opencanal mcp-stdio
```

- 토큰이 없거나 틀리거나 폐기됐으면 `tools/list`는 빈 목록이고, 모든 호출은 `UNAUTHORIZED`다. 기본 사용자로 열리지 않는다.
- `tools/list`에는 내 티어에 허용된 도구만 나온다. 숨긴 도구를 직접 불러도 `TIER_FORBIDDEN`이다.
- 모든 `tools/call` 결과는 텍스트 블록 하나이고, 그 내용은 JSON envelope(`{"ok": true, ...}` 또는 `{"ok": false, "error": {...}}`)다. 다른 사용자의 내용은 `untrusted_data` 아래에만 있다.
- 서버 로그에는 토큰 앞 6자만 남는다. `GET /health`는 `{"ok": true}`다.

### 매칭 들여다보기 (Pro 이상)

```bash
.venv/bin/opencanal match-explain --token <token> --query "모듈러 건축의 현장 조립 오류를 줄일 아이디어" \
  --host-subbrain-id <subbrain_id> [--mode auto|topic|whole_host]
```

τ 미만 후보까지 순위, 관련도, 거리, 점수(관련도 + `distance_bonus` × 거리, τ 미만은 0), 겹친 용어, 선택 여부, 이유를 표로 보여준다. 거리는 호스트와 후보의 노드 라벨·태그·요약 낱말로 계산한 내용 거리다(0 가까움 ~ 1 멂). 신고한 분야와 제목은 거리에 쓰지 않는다. 행은 쓰인 전략의 순위 순이다(기본 `relevance_with_distance_bonus`는 점수 순). 순위와 τ 비교는 반올림하지 않은 값으로 하고, 표의 숫자는 소수 넷째 자리로 반올림해 보여 준다. 커널을 만들지 않고 사용량도 차감하지 않는다. `--token`을 생략하면 `OPENCANAL_TOKEN`을 쓴다.

### 백업과 복원

```bash
.venv/bin/opencanal backup [--out backups/]                                   # backups/opencanal-<UTC>.db.enc (0600, 마스터 키로 암호화)
.venv/bin/opencanal restore --in backups/opencanal-<UTC>.db.enc --db data/restored.db   # 이미 있는 파일은 덮어쓰지 않는다
```

복원하려면 백업을 만든 마스터 키가 있어야 한다. 키 파일과 백업은 git에 넣지 않는다(`.gitignore`의 `data/`, `backups/`, `*.key`). 백업은 평문 DB 사본을 메모리에서만 만든다(SQLite에 serialize가 없으면 0700 임시 디렉터리의 0600 파일을 쓰고 지운다). 복원은 대상 파일 옆에 0600 임시 파일을 잠깐 만들고 끝나면 지운다.

### 테스트

```bash
.venv/bin/python -m pytest -q
```
