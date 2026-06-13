// opencrab.sh hosted MCP client (JSON-RPC over HTTP).
// ocm_ 토큰은 이 모듈에서만 사용되고 OpenCanal 플랫폼으로는 절대 전송되지 않는다.

import { createHash } from "crypto";
import type { ReceiptIngest } from "@opencanal/shared";

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

  /**
   * 거래 영수증을 사용자 온톨로지에 ingest한다 (학습 메모리, R3).
   * 다음 세션의 personaContext 질의가 거래 이력을 반영하게 된다.
   * 실패는 응답 루프를 막지 않도록 삼킨다(best-effort).
   */
  async ingestReceipt(receipt: ReceiptIngest): Promise<boolean> {
    const conditionLines = (receipt.conditions ?? []).map(
      (c) => `  - ${c.label}: ${c.value}${c.met ? " (이행됨)" : ""}`
    );
    const text = [
      `OpenCanal 거래 영수증 — 상태: ${receipt.status}`,
      receipt.counterpartHandle ? `상대 agent: @${receipt.counterpartHandle}` : null,
      `제안자: @${receipt.proposerHandle}`,
      `합의 조건: ${receipt.terms}`,
      conditionLines.length ? `조건표:\n${conditionLines.join("\n")}` : null,
      receipt.fulfilledAt ? `이행 완료: ${receipt.fulfilledAt}` : null,
      receipt.disputedAt ? `분쟁 제기: ${receipt.disputedAt}` : null,
      `확정 시각: ${receipt.createdAt} · receipt ${receipt.id}`,
    ]
      .filter(Boolean)
      .join("\n");
    try {
      await this.callTool("ontology_ingest", {
        text,
        source: `opencanal:receipt:${receipt.id}`,
      });
      return true;
    } catch {
      return false;
    }
  }
}
