import type { BrainOutput } from "@opencanal/shared";
import { brainOutputSchema } from "@opencanal/shared";

export interface BrainAdapter {
  readonly name: string;
  /** Run one headless completion. systemPrompt = OpenCanal constitution. */
  complete(systemPrompt: string, userPrompt: string): Promise<string>;
}

/** Parse the model's JSON contract; fall back to raw text (held for approval). */
export function parseBrainOutput(raw: string): BrainOutput {
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
    // fall through
  }
  // 계약 위반 출력은 그대로 보내지 않고 승인 대기로 — 안전한 기본값
  return { content: trimmed.slice(0, 8000), needs_approval: true };
}
