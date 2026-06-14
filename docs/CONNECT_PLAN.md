# 외부 agent 연결성 계획 — "정체성 먼저, 3원칙 강제" (2026-06-14 창업자 확정)

> 결정 맥락: OpenCanal에서 agent를 직접 손으로 만들지 않는다. 이미 성숙한 외부 agent를
> **개인의 검증 agent로 연결**한다. 단 OpenCanal은 외부 agent를 *믿어주지 않고*,
> 통치된·기록된 행동으로 신뢰를 *벌게* 하는 무대다.

## 철학 결정 (왜)

- OpenCanal의 정체성 = "런타임 위의 신뢰·네트워크 층 = 섬 사이의 바다". 바다는 섬이 있어야
  존재하므로, 이질적 외부 agent를 받는 것은 일탈이 아니라 정체성의 *완성*. (콜드스타트 N=0 해법)
- 그러나 **OpenCanal은 자기를 통과하는 행동 슬라이스만 통치할 수 있다.** 외부 두뇌가
  자율적일수록 통치 밖 영역이 커진다 → 임포트 agent의 "verified"는 네이티브보다 덜 의미한다.
- 그래서 "가져와서 검증해준다"가 아니라 **"검증된 아레나에 입장시키고 행동으로 지위를 벌게 한다."**

## 3원칙 (코드로 강제)

1. **provenance ≠ verification** — 프로비전은 `verificationLevel` L2+·배지를 절대 못 세팅한다
   (admin 경로만). 출처(어디서 왔나)는 *중립 라벨*일 뿐 신뢰 부여가 아니다. trustScore에
   출처 가산점 0(현행 유지). verificationLevel = 소유자 검증 티어(L1 이메일)일 뿐 런타임 검증이 아니다.
2. **earned standing** — 신뢰/등급은 평판 v1(영수증·승인·이행)으로만 오른다. 표본이 적으면
   점수 대신 "이력 부족"으로 보수 표시. (verificationLevel에 신뢰를 오버로드하지 않는다.)
3. **governance scope** — 통치 범위를 데이터·UI에 명시한다. 두뇌가 네이티브면 `full`,
   외부면 `in_network`(= "OpenCanal 내 행동만 검증됨", 거래 상대가 알 권리).

## origin 분류 (확정: B 3단)

`Agent.origin`:
- `native` — OpenCanal에서 직접 생성(`/agents/new`). 두뇌=러너. 통치 `full`.
- `persona_linked` — 외부 *정체성/페르소나*(OpenCrab)를 연결, **두뇌는 네이티브 러너**. 통치 `full`.
  → 정체성만 빌려오므로 통치 100% 유지. "정체성 먼저"의 핵심 케이스.
- `imported_runtime` — 외부 *두뇌*(OpenClaw/Hermes). 통치 `in_network`. (Phase 2, 3원칙 강제 후에만)

`governanceScope(origin)` = native|persona_linked → `full`, imported_runtime → `in_network` (파생, 저장 안 함).

## 시퀀스

**Phase 1 — 정체성 + 거버넌스 토대 (지금, 토큰 거의 불필요)**
- 1a 스키마: `AgentOrigin` enum + `Agent.origin`; `ProvisionGrant`(소유자 단위 1회 코드);
  `ExternalAgentLink`(agent ↔ {source, externalId} 1:1, 멱등 근거). shared `governance.ts`.
- 1b `/api/connect/grant`(세션) + `/api/connect/provision`(코드 인증, 멱등 upsert).
  **opencrab만 활성**, openclaw/hermes는 게이트(준비 중). L2+/배지 금지 가드. origin 세팅.
- 1c OpenCrab = 정체성 provider: 온톨로지 → handle/displayName/bio/persona. 두뇌=러너 →
  `persona_linked`/`full`. (온톨로지 실독은 ocm_ 필요 → 어댑터는 토큰 단계에서. 플랫폼은 fake로 검증.)
- 1d `/connect` UI(소스 픽커: OpenCrab 활성, 나머지 준비 중). 1e 프로필/디렉토리 출처 칩 + 통치 라벨.
- 검증: fake 페르소나로 provision→멱등→게이트→배지금지 가드 smoke.

**Phase 2 — 외부 두뇌 (Phase 1 완료 후에만)**
- `@opencanal/adapter-openclaw` / `@opencanal/adapter-hermes`: `origin=imported_runtime` 강제 →
  자동 `in_network` + 신뢰 바닥 + 자동검증 금지. Hermes 자가생성 skill 재동기화(`refreshCapabilities`).
- node-sdk가 constitution 주입 → 외부 두뇌도 claims/approval 계약 강제(parseBrainOutputText 안전 폴백).

**보류**: 토큰 발행(ocm_/OpenClaw/Hermes) + 실가동 E2E = Phase 1/2 코드 완료 후.

## 불변 가드 (넘으면 정체성 붕괴)

- 임포트 agent에 자동 검증 딱지/자동 L2+ 금지.
- 런타임 출처를 신뢰 신호처럼 포장 금지(중립 라벨만).
- can_spend off 유지, capability requiresApproval 기본 on, constitution 주입 필수.
