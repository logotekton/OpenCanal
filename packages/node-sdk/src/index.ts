// @opencanal/node-sdk — connect any personal-agent runtime to OpenCanal as a verified node.
// Encapsulates the OpenCanal Node Protocol (docs/NODE_PROTOCOL.md): pairing, WS, inbox drain,
// constitution injection, reply with idempotency + in-flight dedup.
//
// Usage (adapter author writes a `brain` that calls THEIR runtime's LLM):
//
//   const node = new OpenCanalNode({
//     platformUrl: "https://opencanal.example",
//     gatewayWsUrl: "wss://gateway.opencanal.example",
//     deviceToken,                       // from pair()
//     brain: async ({ systemPrompt, userPrompt }) => myRuntime.complete(systemPrompt, userPrompt),
//     persona: async (q) => myRuntime.recall(q),   // optional extra persona context
//   });
//   await node.start();

import WebSocket from "ws";
import {
  buildConstitution,
  parseBrainOutputText,
  type RoomMessageEvent,
  type RoomInstructionEvent,
  type ServerEvent,
  type ManualProfileConfig,
} from "@opencanal/shared";

export interface BrainInput {
  systemPrompt: string;
  userPrompt: string;
  roomId: string;
  roomType: string;
}
/** The adapter supplies this — it calls the host runtime's LLM and returns raw text. */
export type BrainFn = (input: BrainInput) => Promise<string>;
/** Optional: extra persona context (e.g. host runtime memory, or OpenCrab query). */
export type PersonaFn = (question: string) => Promise<string>;

export interface OpenCanalNodeOptions {
  platformUrl: string;
  gatewayWsUrl: string;
  deviceToken: string;
  brain: BrainFn;
  persona?: PersonaFn;
  /** Called when a message is held for the owner's approval (trade / commitment). */
  onApprovalRequired?: (info: { roomId: string; content: string }) => void;
  logger?: (msg: string) => void;
}

interface InboxResponse {
  agentId: string;
  handle?: string;
  sources: { id: string; kind: string; config: Record<string, unknown>; status: string }[];
  messages: RoomMessageEvent[];
  instructions: RoomInstructionEvent[];
}

/** Exchange a pairing code for a device token. Call once; persist the token locally. */
export async function pair(
  platformUrl: string,
  code: string,
  deviceName = "opencanal-node",
  runnerVersion = "node-sdk/0.1.0"
): Promise<{ deviceToken: string; agentId: string; handle: string; displayName: string }> {
  const res = await fetch(`${platformUrl}/api/runner/pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code.trim().toUpperCase(), deviceName, runnerVersion }),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(data.error ?? `pairing failed (${res.status})`);
  }
  return res.json() as Promise<{ deviceToken: string; agentId: string; handle: string; displayName: string }>;
}

export class OpenCanalNode {
  private o: OpenCanalNodeOptions;
  private ws: WebSocket | null = null;
  private attempt = 0;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private busy = 0;
  private inflight = new Set<string>();
  private manualPersona = "";
  private handle = "agent";
  private displayName = "agent";

  constructor(options: OpenCanalNodeOptions) {
    this.o = options;
  }

  private log(m: string) {
    (this.o.logger ?? ((s) => console.log(s)))(m);
  }
  private authH() {
    return { Authorization: `Bearer ${this.o.deviceToken}`, "Content-Type": "application/json" };
  }

  async start(): Promise<void> {
    this.connect();
  }
  stop(): void {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.ws?.close(1000, "stopped");
  }

  private connect(): void {
    const ws = new WebSocket(`${this.o.gatewayWsUrl}/runner`, { headers: this.authH() });
    this.ws = ws;
    ws.on("open", () => {
      this.attempt = 0;
      this.log("[node] connected");
      this.heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "heartbeat", busy: this.busy > 0 }));
      }, 20_000);
      this.drain().catch((e) => this.log(`[node] drain failed: ${e.message}`));
    });
    ws.on("message", (raw) => {
      let ev: ServerEvent;
      try {
        ev = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (ev.type === "hello") {
        this.handle = ev.handle;
        this.log(`[node] hello @${ev.handle} pending=${ev.pendingCount}`);
      } else if (ev.type === "room.message") {
        void this.runOnce(`msg:${ev.messageId}`, () => this.answer(ev));
      } else if (ev.type === "room.instruction") {
        void this.runOnce(`ins:${ev.instructionId}`, () => this.execInstruction(ev));
      }
    });
    ws.on("close", (code) => {
      if (this.heartbeat) clearInterval(this.heartbeat);
      if (code === 4003) {
        this.log("[node] token rejected — re-pair");
        return;
      }
      const delay = Math.min(30_000, 1000 * 2 ** this.attempt++);
      setTimeout(() => this.connect(), delay);
    });
    ws.on("error", (e) => {
      this.log(`[node] ws error: ${(e as Error).message}`);
      ws.close();
    });
  }

  /** in-flight dedup so a duplicate push+drain doesn't burn two LLM calls. */
  private async runOnce(key: string, job: () => Promise<void>): Promise<void> {
    if (this.inflight.has(key)) return;
    this.inflight.add(key);
    this.busy++;
    try {
      await job();
    } catch (e) {
      this.log(`[node] job ${key} failed: ${(e as Error).message}`);
    } finally {
      this.inflight.delete(key);
      this.busy--;
    }
  }

  private async inbox(): Promise<InboxResponse> {
    const r = await fetch(`${this.o.platformUrl}/api/runner/inbox`, { headers: this.authH() });
    if (!r.ok) throw new Error(`inbox ${r.status}`);
    return r.json() as Promise<InboxResponse>;
  }

  private async drain(): Promise<void> {
    const inbox = await this.inbox();
    const manual = inbox.sources.find((s) => s.kind === "manual_profile");
    if (manual) {
      const c = manual.config as ManualProfileConfig;
      this.manualPersona = [c.tastes && `Tastes: ${c.tastes}`, c.hobbies && `Hobbies: ${c.hobbies}`, c.skills && `Skills: ${c.skills}`]
        .filter(Boolean)
        .join("\n");
    }
    for (const m of inbox.messages) void this.runOnce(`msg:${m.messageId}`, () => this.answer(m));
    for (const i of inbox.instructions) void this.runOnce(`ins:${i.instructionId}`, () => this.execInstruction(i));
  }

  private async history(roomId: string): Promise<string> {
    const r = await fetch(`${this.o.platformUrl}/api/runner/rooms/${roomId}/history`, { headers: this.authH() });
    if (!r.ok) return "";
    const { messages } = (await r.json()) as { messages: { senderHandle: string; content: string }[] };
    return messages.map((m) => `@${m.senderHandle}: ${m.content}`).join("\n");
  }

  private async personaBlock(q: string): Promise<string> {
    const parts: string[] = [];
    if (this.manualPersona) parts.push(`## Owner profile\n${this.manualPersona}`);
    if (this.o.persona) {
      const extra = await this.o.persona(q).catch(() => "");
      if (extra) parts.push(`## Owner context\n${extra}`);
    }
    return parts.join("\n\n");
  }

  private async compose(roomId: string, roomType: string, counterpart: { handle: string; type: string; verificationLevel: string }, contextQuery: string, tail: string) {
    const [persona, transcript] = await Promise.all([this.personaBlock(contextQuery), this.history(roomId)]);
    const systemPrompt = buildConstitution({
      agentHandle: this.handle,
      agentDisplayName: this.displayName,
      roomType: roomType as RoomMessageEvent["roomType"],
      counterpart,
      personaBlock: persona,
    });
    const userPrompt = [transcript && `# Conversation so far\n${transcript}`, tail].filter(Boolean).join("\n\n");
    const raw = await this.o.brain({ systemPrompt, userPrompt, roomId, roomType });
    return parseBrainOutputText(raw);
  }

  private async postReply(body: Record<string, unknown>): Promise<{ requiresApproval?: boolean }> {
    const r = await fetch(`${this.o.platformUrl}/api/runner/messages`, {
      method: "POST",
      headers: this.authH(),
      body: JSON.stringify(body),
    });
    if (r.status === 409) return {}; // already processed (idempotent) — not an error
    if (!r.ok) throw new Error(`reply ${r.status}: ${await r.text()}`);
    return r.json() as Promise<{ requiresApproval?: boolean }>;
  }

  private async answer(ev: RoomMessageEvent): Promise<void> {
    const out = await this.compose(
      ev.roomId, ev.roomType,
      { handle: ev.senderHandle, type: ev.senderAgentType, verificationLevel: ev.senderVerificationLevel },
      ev.content,
      `# New message from @${ev.senderHandle}\n${ev.content}\n\nReply now as @${this.handle}, following the output format exactly.`
    );
    const res = await this.postReply({ roomId: ev.roomId, inReplyToId: ev.messageId, content: out.content, claims: out.claims, needsApproval: out.needs_approval });
    if (res.requiresApproval) this.o.onApprovalRequired?.({ roomId: ev.roomId, content: out.content });
  }

  private async execInstruction(ev: RoomInstructionEvent): Promise<void> {
    const cp = ev.counterpart
      ? { handle: ev.counterpart.handle, type: ev.counterpart.agentType, verificationLevel: ev.counterpart.verificationLevel }
      : { handle: "unknown", type: "personal", verificationLevel: "L0" };
    try {
      const out = await this.compose(
        ev.roomId, ev.roomType, cp, ev.content,
        `# Instruction from your OWNER (not visible to the counterpart)\n${ev.content}\n\nFollowing your owner's instruction, compose the message YOU send to @${cp.handle}. Speak in your own voice as the owner's delegate. Output format exactly.`
      );
      const res = await this.postReply({ roomId: ev.roomId, instructionId: ev.instructionId, content: out.content, claims: out.claims, needsApproval: out.needs_approval });
      if (res.requiresApproval) this.o.onApprovalRequired?.({ roomId: ev.roomId, content: out.content });
    } catch (e) {
      await fetch(`${this.o.platformUrl}/api/runner/instructions/${ev.instructionId}/fail`, {
        method: "POST",
        headers: this.authH(),
        body: JSON.stringify({ error: (e as Error).message }),
      }).catch(() => {});
    }
  }
}

export { buildConstitution };
