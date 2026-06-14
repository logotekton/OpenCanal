// opencrab.sh hosted MCP client (JSON-RPC over HTTP).
// ocm_ 토큰은 이 모듈에서만 사용되고 OpenCanal 플랫폼으로는 절대 전송되지 않는다.
// 실제 도구명(opencrab.sh, 2026-06 라이브 검증): opencrab_query / opencrab_ingest_text / opencrab_status.

import { createHash } from "crypto";
import type { ReceiptIngest } from "@opencanal/shared";

interface McpResult {
  content?: { type: string; text?: string }[];
  isError?: boolean;
}

export class OpencrabClient {
  private url: string;
  private nextId = 1;
  private sessionId: string | null = null;
  private initialized = false;

  constructor(token: string, mcpUrl?: string) {
    this.url = mcpUrl ?? `https://opencrab.sh/api/mcp/${token}`;
  }

  private async post(method: string, params: Record<string, unknown>, isNotification = false): Promise<Response> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    };
    if (this.sessionId) headers["Mcp-Session-Id"] = this.sessionId;
    return fetch(this.url, {
      method: "POST",
      headers,
      body: JSON.stringify({ jsonrpc: "2.0", ...(isNotification ? {} : { id: this.nextId++ }), method, params }),
      signal: AbortSignal.timeout(30_000),
    });
  }

  // 일부 MCP HTTP 서버는 tools/call 전에 initialize를 요구한다 (세션 발급). 스테이트리스 서버엔 무해.
  private async ensureInit(): Promise<void> {
    if (this.initialized) return;
    const res = await this.post("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "opencanal-runner", version: "0.1.0" },
    });
    const sid = res.headers.get("mcp-session-id");
    if (sid) this.sessionId = sid;
    this.initialized = true;
    if (this.sessionId) await this.post("notifications/initialized", {}, true).catch(() => {});
  }

  private async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    await this.ensureInit();
    const res = await this.post("tools/call", { name, arguments: args });
    if (!res.ok) throw new Error(`opencrab.sh HTTP ${res.status}`);

    const contentType = res.headers.get("content-type") ?? "";
    let payload: { result?: McpResult; error?: { message: string } };
    if (contentType.includes("text/event-stream")) {
      const text = await res.text();
      const dataLines = text.split("\n").filter((l) => l.startsWith("data:"));
      payload = JSON.parse(dataLines[dataLines.length - 1].slice(5));
    } else {
      payload = await res.json();
    }

    if (payload.error) throw new Error(`opencrab error: ${payload.error.message}`);
    const textPart = payload.result?.content?.find((c) => c.type === "text")?.text ?? "";
    // 도구 레벨 오류(isError)는 텍스트를 메시지로 던진다 — 호출부가 graceful 처리
    if (payload.result?.isError) throw new Error(`opencrab tool error: ${textPart.slice(0, 200)}`);
    return textPart;
  }

  /** Validate the token + connectivity (opencrab_status). Returns attestation metadata. */
  async validateAndAttest(packId: string): Promise<{
    packId: string;
    manifestHash: string;
    spaces: string[];
  }> {
    const statusText = await this.callTool("opencrab_status", {});
    const manifestHash = createHash("sha256").update(statusText).digest("hex").slice(0, 16);
    return { packId, manifestHash, spaces: [] };
  }

  /**
   * Query the user's ontology for persona context (opencrab_query).
   * workspaceId로 스코프하면 대형 테넌트의 statement timeout을 피하고 해당 페르소나만 검색한다.
   */
  async personaContext(question: string, limit = 5, workspaceId?: string): Promise<string> {
    try {
      const args: Record<string, unknown> = { query: question, top_k: limit };
      if (workspaceId) args.workspace_id = workspaceId;
      const resultText = await this.callTool("opencrab_query", args);
      return resultText.slice(0, 4000);
    } catch (err) {
      return `(OpenCrab query failed: ${err instanceof Error ? err.message : String(err)})`;
    }
  }

  /** Ingest arbitrary text into the ontology (opencrab_ingest_text). Returns workspace/package ids. */
  async ingestText(
    title: string,
    content: string,
    createPack = false
  ): Promise<{ workspaceId: string | null; packageId: string | null }> {
    const text = await this.callTool("opencrab_ingest_text", { title, content, create_pack: createPack });
    try {
      const j = JSON.parse(text) as { workspace_id?: string; package_id?: string; package?: { package_id?: string } };
      return { workspaceId: j.workspace_id ?? null, packageId: j.package?.package_id ?? j.package_id ?? null };
    } catch {
      return { workspaceId: null, packageId: null };
    }
  }

  /**
   * 거래 영수증을 사용자 온톨로지에 ingest한다 (학습 메모리, R3 — opencrab_ingest_text).
   * create_pack:false — 영수증마다 팩을 만들지 않고 그래프만 갱신. 실패는 응답 루프를 막지 않게 삼킨다.
   */
  async ingestReceipt(receipt: ReceiptIngest): Promise<boolean> {
    const conditionLines = (receipt.conditions ?? []).map(
      (c) => `  - ${c.label}: ${c.value}${c.met ? " (이행됨)" : ""}`
    );
    const content = [
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
      await this.ingestText(`OpenCanal 거래 영수증 ${receipt.id} (${receipt.status})`, content, false);
      return true;
    } catch {
      return false;
    }
  }
}
