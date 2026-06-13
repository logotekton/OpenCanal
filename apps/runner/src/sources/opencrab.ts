// opencrab.sh hosted MCP client (JSON-RPC over HTTP).
// ocm_ 토큰은 이 모듈에서만 사용되고 OpenCanal 플랫폼으로는 절대 전송되지 않는다.

import { createHash } from "crypto";

interface McpToolResult {
  content?: { type: string; text?: string }[];
  isError?: boolean;
}

export class OpencrabClient {
  private url: string;
  private nextId = 1;

  constructor(token: string, mcpUrl?: string) {
    this.url = mcpUrl ?? `https://opencrab.sh/api/mcp/${token}`;
  }

  private async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    const res = await fetch(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: this.nextId++,
        method: "tools/call",
        params: { name, arguments: args },
      }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) throw new Error(`opencrab.sh HTTP ${res.status}`);

    const contentType = res.headers.get("content-type") ?? "";
    let payload: { result?: McpToolResult; error?: { message: string } };
    if (contentType.includes("text/event-stream")) {
      // Some MCP HTTP servers stream — take the last data: line
      const text = await res.text();
      const dataLines = text.split("\n").filter((l) => l.startsWith("data:"));
      payload = JSON.parse(dataLines[dataLines.length - 1].slice(5));
    } else {
      payload = await res.json();
    }

    if (payload.error) throw new Error(`opencrab error: ${payload.error.message}`);
    const textPart = payload.result?.content?.find((c) => c.type === "text")?.text;
    return textPart ?? "";
  }

  /** Validate the token + fetch grammar manifest. Returns attestation metadata. */
  async validateAndAttest(packId: string): Promise<{
    packId: string;
    manifestHash: string;
    spaces: string[];
  }> {
    const manifestText = await this.callTool("ontology_manifest", {});
    const manifestHash = createHash("sha256").update(manifestText).digest("hex").slice(0, 16);
    let spaces: string[] = [];
    try {
      const manifest = JSON.parse(manifestText);
      spaces = Array.isArray(manifest.spaces)
        ? manifest.spaces.map((s: { name?: string } | string) =>
            typeof s === "string" ? s : (s.name ?? "")
          )
        : Object.keys(manifest.spaces ?? {});
    } catch {
      // manifest not JSON — keep hash only
    }
    return { packId, manifestHash, spaces };
  }

  /** Query the user's ontology for persona context relevant to a question. */
  async personaContext(question: string, limit = 5): Promise<string> {
    try {
      const resultText = await this.callTool("ontology_query", { question, limit });
      return resultText.slice(0, 4000);
    } catch (err) {
      return `(OpenCrab query failed: ${err instanceof Error ? err.message : String(err)})`;
    }
  }
}
