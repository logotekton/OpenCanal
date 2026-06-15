// Codex adapter (EXPERIMENTAL) — spawns `codex exec` with the user's ChatGPT sign-in.
// OpenAI ToS posture is murkier than Claude's; labeled experimental on purpose.

import { spawn } from "child_process";
import type { BrainAdapter } from "./adapter";

export class CodexAdapter implements BrainAdapter {
  readonly name = "codex";

  complete(systemPrompt: string, userPrompt: string): Promise<string> {
    // SECURITY: the prompt contains untrusted counterpart-agent content. It MUST NOT
    // pass through a shell (shell:true would allow command injection / RCE on the
    // user's own machine). We use shell:false and feed the prompt via STDIN so no
    // untrusted text ever appears in argv. The executable is resolved per-platform
    // because shell:false won't resolve a .cmd shim on Windows.
    const fullPrompt = `${systemPrompt}\n\n---\n\n${userPrompt}`;
    const bin = process.platform === "win32" ? "codex.cmd" : "codex";
    return new Promise((resolve, reject) => {
      const child = spawn(bin, ["exec", "--skip-git-repo-check", "-"], {
        shell: false,
        timeout: 120_000,
        stdio: ["pipe", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (d) => (stdout += d.toString()));
      child.stderr.on("data", (d) => (stderr += d.toString()));
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0 && stdout.trim()) resolve(stdout.trim());
        else reject(new Error(`codex exec failed (${code}): ${stderr.slice(0, 500)}`));
      });
      // Untrusted content goes only to stdin, never to argv/shell.
      child.stdin.write(fullPrompt);
      child.stdin.end();
    });
  }
}
