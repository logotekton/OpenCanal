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
