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

// ── Brain output contract ──
export const brainOutputSchema = z.object({
  content: z.string(),
  claims: z.array(claimSchema).optional(),
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
  return { content: trimmed.slice(0, 8000), needs_approval: true };
}
