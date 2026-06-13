// Claude adapter — headless via Claude Agent SDK.
// 인증: 사용자의 기존 Claude Code 로그인(구독) 또는 CLAUDE_CODE_OAUTH_TOKEN(`claude setup-token`).
// API 키 불필요, 추가 과금 없음. 자격증명은 SDK/CLI가 로컬에서 관리한다.

import { query } from "@anthropic-ai/claude-agent-sdk";
import type { BrainAdapter } from "./adapter";

export class ClaudeAdapter implements BrainAdapter {
  readonly name = "claude";

  async complete(systemPrompt: string, userPrompt: string): Promise<string> {
    let result = "";
    const q = query({
      prompt: userPrompt,
      options: {
        systemPrompt,
        maxTurns: 1,
        allowedTools: [], // 채팅 응답 전용 — 파일/셸 도구 비활성
        permissionMode: "default",
      },
    });
    for await (const message of q) {
      if (message.type === "result") {
        if (message.subtype === "success") {
          result = message.result;
        } else {
          throw new Error(`claude brain failed: ${message.subtype}`);
        }
      }
    }
    if (!result) throw new Error("claude brain returned empty result");
    return result;
  }
}
