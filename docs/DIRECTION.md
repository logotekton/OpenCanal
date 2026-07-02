# DIRECTION — 피벗 v1 (2026-07-02)

> **한 줄**: OpenCanal은 이제 **personal agent 검증장(proving ground)**이다.
> 내 PAB 페르소나로 빚은 agent에게 시뮬레이션된 상황을 던지고, 행동을 관찰·교정하고, 그 기록을 증거로 축적한다.
> "내 agent가 정말 나답게 판단하는가"가 증명되기 전까지, 네트워크는 없다.

## 무엇이 바뀌었나

**미션은 불변**: AGI 시대에 개인의 agent가 개인을 대신한다.

**바뀐 것은 순서다.** v1(OpenCanal 신뢰 네트워크)은 코드가 아니라 전제가 실패했다:

1. 콜드스타트가 구조적 — "agent 간 대화"의 가치는 상대가 존재해야 발생하는데 N=0. 검증 딱지·평판·영수증은 검증할 활동이 없는 인프라였다.
2. 마찰이 가치보다 먼저 — 가입→러너 설치→페어링→브리지를 거쳐 나오는 것이 "대화 초안".
3. 신뢰 계층을 활동보다 먼저 지었다.

v2는 순서를 뒤집는다: **agent 충실도 먼저, 네트워크는 그 다음.**
지금의 자산은 프로토콜 인프라가 아니라 **PAB(Personal Agent Builder)** — 사람을 구조화된 페르소나 팩(decision policies, tacit heuristics, communication style, red flags, workflow playbooks, evaluation cases, domain overlays)으로 증류하는 방법론이다. 플랫폼은 이 자산을 검증하고 키우는 기계여야 한다.

## 제품 = 시뮬레이터, 루프 3개

```
  [Build]                [Prove]                    [Correct]
  OpenCrab PAB 팩   →   시나리오 엔진이 상황 투척   →   소유자가 판단 검수
  → agent 인스턴스화     (합성 상대 agent와           (맞음/틀림/교정)
  (실제 두뇌+헌법)        Intent→Session→Receipt)     → 교정을 팩으로 재ingest
       ↑                                                    │
       └────────────── agent가 더 "나다워짐" ←──────────────┘
```

1. **Build** — OpenCrab의 PAB 팩을 로드해 agent를 인스턴스화한다. 두뇌는 실제(Claude Agent SDK headless, 소유자 구독), constitution 주입 유지.
2. **Prove** — 시나리오 엔진이 소유자의 실제 업무에서 온 상황(협상, 일정 조율, 발주 검토, 고객 문의)을 던진다. 상대방은 합성 counterparty agent. 상호작용은 기존 Intent→Session→Receipt 프로토콜 위에서 이루어진다. PAB의 evaluation cases가 시나리오의 1차 원천.
3. **Correct** — 소유자가 관찰 UI에서 agent의 판단을 검수한다: "이 판단, 나였어도 같았나?" 교정은 OpenCrab 팩으로 재ingest되고(`personal agent evidence`), agent는 회차마다 나다워진다.

## 원칙

- **시뮬레이션되는 것은 세계뿐.** agent·페르소나·상호작용 프로토콜은 처음부터 진짜다. "실제 활동 모드"는 재작성이 아니라 배포 대상 전환이다.
- **N=1에서 완결.** 루프는 사용자 혼자서 가치가 나온다. 네트워크 효과에 기대는 기능은 만들지 않는다.
- **증거가 화폐.** 시나리오 통과 기록·교정 이력·행동 로그가 축적 자산이며, 미래 실모드의 평판/신뢰의 씨앗이다. 신뢰 인프라는 활동이 생긴 뒤에 짓는다.
- **시나리오는 항상 소유자의 실제 업무에서 온다.** 구경거리 마을(agent들이 그냥 노는 것)은 만들지 않는다.

## 하지 말 것 (anti-direction)

- 실모드 전까지 검증 딱지·평판 v1·승인 게이트·텔레그램 브리지 부활 금지.
- 범용 개인 비서 런타임 경쟁 금지 (v1 anti-roadmap 유지 — Moltbot/Hermes의 게임).
- 자동결제·완전자율거래 금지선 유지.

## 성공 기준 (north star)

v1 R0의 기준 — "제3자가 봐도 이 agent가 그 사람을 대리한다고 납득" — 을 반복 가능·측정 가능하게:

- **시나리오 통과율**: evaluation cases에 대해 소유자 승인 판정 비율.
- **교정 수렴**: 회차당 교정 횟수가 감소하는가 (agent가 배우는가).
- **대리 신뢰**: "이 판단 내가 했어도 같았다" 비율.

## 단계

- **S0 — 루프 1회전 (최소 증명)**: 소유자 본인 PAB 팩 1개 + 시나리오 1개로 Build→Prove→Correct→재ingest E2E. 성공 기준: 교정 1건이 팩에 반영되고 재실행에서 행동이 달라진다.
- **S1 — 시나리오 엔진**: evaluation cases 자동 구동, 합성 상대 생성, 시나리오 저작.
- **S2 — 멀티 agent + 증거 대시보드**: 복수 PAB agent 동시 시뮬레이션, 통과율/수렴 지표 노출.
- **S3 — 졸업**: 검증된 agent를 실채널로. 이 시점에 v1 신뢰 인프라(딱지·평판·승인 게이트) 부활을 검토한다.

## 레포 처분

| 구분 | 대상 |
|---|---|
| **남긴다** | `packages/shared`(타입드 Interaction·Intent→Session→Receipt·constitution·parseBrainOutput), `packages/node-sdk`, `packages/db`(모델은 시뮬레이터에 맞게 마이그레이션), OpencrabClient, DESIGN-x.ai.md·DESIGN-tesla.md |
| **동결한다** | `apps/web`의 신뢰 네트워크 화면(딱지·평판·관리자 큐), `apps/bridge`, `apps/runner` 페어링 흐름, 옛 smoke 스크립트 |
| **아카이브** | v1 계획/진행 문서 → `docs/archive/` (ROADMAP, GOAL_PROGRESS, R0~R5 문서 — 삭제하지 않는다, 실패의 기록이 근거다) |
| **새로 만든다** | 시뮬레이터 앱(시나리오 엔진 + 관찰/교정 UI + 재ingest 루프) |

리브랜딩(레포 rename)은 방향이 코드로 굳은 뒤에 한다.
