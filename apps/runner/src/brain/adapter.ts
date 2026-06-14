import { parseBrainOutputText } from "@opencanal/shared";

export interface BrainAdapter {
  readonly name: string;
  /** Run one headless completion. systemPrompt = OpenCanal constitution. */
  complete(systemPrompt: string, userPrompt: string): Promise<string>;
}

/** Parse the model's JSON contract; fall back to raw text (held for approval).
 *  Single source of truth lives in @opencanal/shared (shared with the node SDK). */
export const parseBrainOutput = parseBrainOutputText;
