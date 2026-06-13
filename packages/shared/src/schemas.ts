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

// ── Brain output contract ──
export const brainOutputSchema = z.object({
  content: z.string(),
  claims: z.array(claimSchema).optional(),
  needs_approval: z.boolean().default(false),
});
export type BrainOutput = z.infer<typeof brainOutputSchema>;
