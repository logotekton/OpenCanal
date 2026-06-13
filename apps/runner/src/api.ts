// Platform REST client (device-token auth).

import type { RunnerConfig } from "./config";
import type { RoomMessageEvent, RoomInstructionEvent, AttestSourcePayload } from "@opencanal/shared";

export interface InboxResponse {
  agentId: string;
  sources: { id: string; kind: string; config: Record<string, unknown>; status: string }[];
  messages: RoomMessageEvent[];
  instructions: RoomInstructionEvent[];
}

export class PlatformApi {
  constructor(private config: RunnerConfig) {}

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.config.deviceToken}`,
    };
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${this.config.platformUrl}${path}`, {
      method,
      headers: this.headers(),
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${method} ${path} → ${res.status} ${text.slice(0, 200)}`);
    }
    return res.json() as Promise<T>;
  }

  static async pair(
    platformUrl: string,
    code: string,
    deviceName: string,
    runnerVersion: string
  ): Promise<{ deviceToken: string; agentId: string; handle: string; displayName: string }> {
    const res = await fetch(`${platformUrl}/api/runner/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, deviceName, runnerVersion }),
    });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      throw new Error(data.error ?? `pairing failed (${res.status})`);
    }
    return res.json() as Promise<{
      deviceToken: string;
      agentId: string;
      handle: string;
      displayName: string;
    }>;
  }

  inbox(): Promise<InboxResponse> {
    return this.request("GET", "/api/runner/inbox");
  }

  history(roomId: string): Promise<{ messages: { senderHandle: string; senderAgentId: string; content: string }[] }> {
    return this.request("GET", `/api/runner/rooms/${roomId}/history`);
  }

  attestSource(sourceId: string, payload: AttestSourcePayload): Promise<{ ok: boolean }> {
    return this.request("POST", `/api/runner/sources/${sourceId}/attest`, payload);
  }

  reply(payload: {
    roomId: string;
    inReplyToId?: string;
    instructionId?: string;
    content: string;
    claims?: { type: string; text: string }[];
    needsApproval: boolean;
  }): Promise<{ messageId: string; requiresApproval: boolean }> {
    return this.request("POST", "/api/runner/messages", payload);
  }

  failInstruction(instructionId: string, error: string): Promise<{ ok: boolean }> {
    return this.request("POST", `/api/runner/instructions/${instructionId}/fail`, { error });
  }
}
