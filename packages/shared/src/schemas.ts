import { z } from "zod";

// ── Agent ──
export const agentTypeSchema = z.enum([
  "personal",
  "business",
  "enterprise",
  "government",
  "expert",
]);
export type AgentTypeValue = z.infer<typeof agentTypeSchema>;

export const handleSchema = z
  .string()
  .min(3)
  .max(30)
  .regex(/^[a-z0-9][a-z0-9_-]*$/, "lowercase letters, digits, _ and - only");

export const createAgentSchema = z.object({
  handle: handleSchema,
  displayName: z.string().min(1).max(60),
  type: agentTypeSchema.default("personal"),
  bio: z.string().max(500).optional(),
});

// v1 Mandate 축약형
export const permissionsSchema = z.object({
  can_speak: z.boolean().default(true),
  can_advise: z.boolean().default(true),
  can_negotiate: z.boolean().default(false),
  can_commit: z.boolean().default(false),
  can_spend: z.boolean().default(false),
});
export type AgentPermissions = z.infer<typeof permissionsSchema>;

// ── Philosophy-for-AI 최소형 claims ──
export const claimSchema = z.object({
  type: z.enum(["claim", "evidence", "interpretation", "responsibility"]),
  text: z.string(),
});
export type Claim = z.infer<typeof claimSchema>;

// ── Sources ──
export const sourceKindSchema = z.enum(["opencrab_pack", "manual_profile"]);
export type SourceKind = z.infer<typeof sourceKindSchema>;

export const opencrabSourceConfigSchema = z.object({
  packId: z.string().min(1),
  tenantId: z.string().optional(),
  manifestHash: z.string().optional(),
  nodeCount: z.number().optional(),
  spaces: z.array(z.string()).optional(),
  attestedAt: z.string().optional(),
});
export type OpencrabSourceConfig = z.infer<typeof opencrabSourceConfigSchema>;

export const manualProfileConfigSchema = z.object({
  tastes: z.string().max(2000).optional(),
  hobbies: z.string().max(2000).optional(),
  skills: z.string().max(2000).optional(),
  values: z.string().max(2000).optional(),
  extra: z.string().max(4000).optional(),
});
export type ManualProfileConfig = z.infer<typeof manualProfileConfigSchema>;

// ── Rooms ──
export const roomTypeSchema = z.enum(["question", "discussion", "trade", "help"]);
export type RoomTypeValue = z.infer<typeof roomTypeSchema>;

export const createRoomSchema = z.object({
  type: roomTypeSchema.default("question"),
  targetAgentId: z.string().min(1),
  initiatorAgentId: z.string().min(1),
  title: z.string().max(120).optional(),
  intentId: z.string().optional(), // ROOM_REDESIGN Bend 2: 이 룸이 이행하는 Intent
});

// ── Intent (ROOM_REDESIGN Bend 2) ──
export const intentKindSchema = z.enum(["question", "advice", "trade", "debate", "help"]);
export type IntentKind = z.infer<typeof intentKindSchema>;
export const createIntentSchema = z.object({
  onBehalfOfId: z.string().min(1), // 대리할 내 agent
  kind: intentKindSchema.default("question"),
  spec: z.record(z.any()).default({}), // { goal, constraints?, budget?, vertical? }
});

export const postMessageSchema = z.object({
  content: z.string().min(1).max(8000),
  claims: z.array(claimSchema).optional(),
});

// ── BotContract 조건표 (R4 Commerce Room) ──
// 합의를 자유 텍스트(terms)뿐 아니라 구조화된 조건으로 기록한다. met은 이행 단계에서 채워진다.
export const receiptConditionSchema = z.object({
  label: z.string().min(1).max(120),
  value: z.string().max(500).default(""),
  met: z.boolean().optional(),
});
export type ReceiptCondition = z.infer<typeof receiptConditionSchema>;
export const receiptConditionsSchema = z.array(receiptConditionSchema).max(20);

// 숙박/예약 vertical 최소형 — v1 Phase 4 BotContract agreed_terms 라벨 셋
export const LODGING_TEMPLATE: readonly string[] = [
  "체크인 날짜",
  "체크아웃 날짜",
  "인원",
  "총 가격",
  "취소 정책",
  "주차",
];

// ── 능력(capability) 생태계 (R5) ──
// agent가 수행할 수 있다고 선언하는 skill. 어댑터가 외부 런타임 skill을 이 형태로 매핑한다.
// requiresApproval 기본 on — 모든 능력은 승인 봉투 안에서만 실행된다.
export const capabilityDeclSchema = z.object({
  key: z
    .string()
    .min(1)
    .max(80)
    .regex(/^[a-z0-9][a-z0-9._-]*$/i, "key: letters/digits/._- only"),
  label: z.string().min(1).max(120),
  description: z.string().max(500).optional(),
  requiresApproval: z.boolean().default(true),
});
export type CapabilityDecl = z.infer<typeof capabilityDeclSchema>;

export const capabilitiesSyncSchema = z.object({
  capabilities: z.array(capabilityDeclSchema).max(50),
});

// ── 외부 agent 연결(provision-by-connection) (docs/CONNECT_PLAN.md) ──
// 외부 런타임/온톨로지가 자기 정체성으로 OpenCanal 검증 agent를 프로비전한다.
export const provisionExternalSchema = z.object({
  externalId: z.string().min(1).max(200), // 출처 시스템에서의 agent id (멱등 키)
  handle: handleSchema,
  displayName: z.string().min(1).max(60),
  bio: z.string().max(500).optional(),
  type: agentTypeSchema.default("personal"),
  externalUrl: z.string().url().max(300).optional(),
  capabilities: z.array(capabilityDeclSchema).max(50).optional(),
});
export type ProvisionExternal = z.infer<typeof provisionExternalSchema>;

export const provisionBodySchema = z.object({
  code: z.string().min(1),
  source: z.enum(["opencrab", "openclaw", "hermes"]),
  external: provisionExternalSchema,
  runnerVersion: z.string().optional(),
});

// ── 타입드 Interaction (docs/ROOM_REDESIGN.md Bend 1) ──
// agent 발화의 "행위 종류". prose 채팅이 아니라 구조화된 상호작용으로 다루기 위한 1차 분류.
export const interactionTypeSchema = z.enum([
  "statement", // 일반 발화(기본)
  "claim",
  "evidence",
  "interpretation",
  "counterclaim",
  "proposal",
  "offer",
  "counteroffer",
  "mandate",
  "decision",
  "system",
]);
export type InteractionType = z.infer<typeof interactionTypeSchema>;

// ── Brain output contract ──
export const brainOutputSchema = z.object({
  // Bend 1: 발화의 행위 종류. 두뇌가 안 주면 statement로 안전 기본.
  type: interactionTypeSchema.default("statement"),
  content: z.string(),
  claims: z.array(claimSchema).optional(),
  // 구조화 페이로드(offer terms, 책임/근거 등) — 사람용 content와 별개의 기계용 표현(JSON 패스스루).
  payload: z.record(z.any()).optional(),
  needs_approval: z.boolean().default(false),
});
export type BrainOutput = z.infer<typeof brainOutputSchema>;

/**
 * Parse a brain's raw text into the {content, claims?, needs_approval} contract.
 * Tolerates markdown code fences and surrounding prose. Contract-violating output
 * is returned verbatim with needs_approval=true (safe default — held for the owner).
 * Shared by the local runner and any external node adapter (@opencanal/node-sdk).
 */
export function parseBrainOutputText(raw: string): BrainOutput {
  const trimmed = raw
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```\s*$/, "");
  try {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) {
      const parsed = brainOutputSchema.safeParse(JSON.parse(trimmed.slice(start, end + 1)));
      if (parsed.success) return parsed.data;
    }
  } catch {
    // fall through to safe default
  }
  return { type: "statement", content: trimmed.slice(0, 8000), needs_approval: true };
}
