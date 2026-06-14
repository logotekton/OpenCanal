// agent 출처와 통치 범위 (docs/CONNECT_PLAN.md). prisma의 AgentOrigin enum과 값 동기 유지.
// 핵심 원칙: 출처(origin)는 *중립 라벨*이며 검증(verificationLevel)이 아니다.

export type AgentOrigin = "native" | "persona_linked" | "imported_runtime";
export type GovernanceScope = "full" | "in_network";

// 통치 범위는 두뇌 출처로 갈린다 — 외부 두뇌만 in_network(= OpenCanal 내 행동만 통치). 파생값(저장 안 함).
export function governanceScope(origin: AgentOrigin): GovernanceScope {
  return origin === "imported_runtime" ? "in_network" : "full";
}

export const PROVISION_SOURCES = ["opencrab", "openclaw", "hermes"] as const;
export type ProvisionSource = (typeof PROVISION_SOURCES)[number];

// Phase 1: opencrab(정체성만, 두뇌 네이티브)만 활성. 외부 두뇌는 3원칙 강제 후(Phase 2) 개방.
export const ACTIVE_PROVISION_SOURCES: ProvisionSource[] = ["opencrab"];

// opencrab = 정체성만 빌려옴(두뇌 네이티브) → persona_linked. 나머지는 외부 두뇌 → imported_runtime.
export function originForSource(source: ProvisionSource): AgentOrigin {
  return source === "opencrab" ? "persona_linked" : "imported_runtime";
}

// UI 라벨 — 중립 출처 표기(검증 신호 아님)
export const ORIGIN_LABEL: Record<AgentOrigin, string> = {
  native: "네이티브",
  persona_linked: "정체성 연결",
  imported_runtime: "외부 런타임",
};
export const SOURCE_LABEL: Record<ProvisionSource, string> = {
  opencrab: "OpenCrab",
  openclaw: "OpenClaw",
  hermes: "Hermes",
};
