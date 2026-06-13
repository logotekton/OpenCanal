// The answer loop: incoming room message OR owner instruction → persona context
// → constitution prompt → headless brain → reply (auto, or held for human approval).

import {
  buildConstitution,
  type RoomMessageEvent,
  type RoomInstructionEvent,
  type ManualProfileConfig,
  type BrainOutput,
} from "@opencanal/shared";
import type { RunnerConfig } from "./config";
import { PlatformApi, type InboxResponse } from "./api";
import { OpencrabClient } from "./sources/opencrab";
import type { BrainAdapter } from "./brain/adapter";
import { parseBrainOutput } from "./brain/adapter";
import { RoomQueue } from "./queue";

interface CounterpartCard {
  handle: string;
  type: string;
  verificationLevel: string;
}

export class AgentLoop {
  private opencrab: OpencrabClient | null;
  private manualPersona = "";
  readonly queue: RoomQueue;

  constructor(
    private config: RunnerConfig,
    private api: PlatformApi,
    private brain: BrainAdapter,
    private agentMeta: { handle: string; displayName: string }
  ) {
    this.opencrab = config.opencrab?.token
      ? new OpencrabClient(config.opencrab.token, config.opencrab.mcpUrl)
      : null;
    this.queue = new RoomQueue(config.limits.concurrency, config.limits.repliesPerHour);
  }

  /** Load manual_profile source content from the platform (non-secret). */
  syncSources(sources: InboxResponse["sources"]): void {
    const manual = sources.find((s) => s.kind === "manual_profile");
    if (manual) {
      const c = manual.config as ManualProfileConfig;
      this.manualPersona = [
        c.tastes && `Tastes: ${c.tastes}`,
        c.hobbies && `Hobbies: ${c.hobbies}`,
        c.skills && `Skills: ${c.skills}`,
        c.values && `Values: ${c.values}`,
        c.extra && c.extra,
      ]
        .filter(Boolean)
        .join("\n");
    }
  }

  // 같은 항목이 WS push와 재접속 drain으로 동시에 들어와도 LLM(compose)을 한 번만 돌리도록
  // in-flight 데듀프. 작업 완료 시 해제하므로, 실패로 서버에 pending이 남아 재드레인되는 경우의
  // 정상 재시도는 막지 않는다.
  private inflight = new Set<string>();

  private runOnce(key: string, roomId: string, job: () => Promise<void>): void {
    if (this.inflight.has(key)) return;
    this.inflight.add(key);
    this.queue.enqueue(roomId, async () => {
      try {
        await job();
      } finally {
        this.inflight.delete(key);
      }
    });
  }

  handleMessage(event: RoomMessageEvent): void {
    this.runOnce(`msg:${event.messageId}`, event.roomId, () => this.answer(event));
  }

  handleInstruction(event: RoomInstructionEvent): void {
    this.runOnce(`ins:${event.instructionId}`, event.roomId, () => this.executeInstruction(event));
  }

  private async personaBlock(question: string): Promise<string> {
    const parts: string[] = [];
    if (this.manualPersona) parts.push(`## Owner profile (self-written)\n${this.manualPersona}`);
    if (this.opencrab) {
      const ctx = await this.opencrab.personaContext(question);
      if (ctx) parts.push(`## Owner ontology (OpenCrab, pack: ${this.config.opencrab?.packId})\n${ctx}`);
    }
    return parts.join("\n\n");
  }

  /** Shared pipeline: persona + history + constitution → brain → parsed output. */
  private async compose(
    roomId: string,
    roomType: RoomMessageEvent["roomType"],
    counterpart: CounterpartCard,
    contextQuery: string,
    promptTail: string
  ): Promise<BrainOutput> {
    const [persona, history] = await Promise.all([
      this.personaBlock(contextQuery),
      this.api.history(roomId).catch(() => ({ messages: [] })),
    ]);

    const systemPrompt = buildConstitution({
      agentHandle: this.agentMeta.handle,
      agentDisplayName: this.agentMeta.displayName,
      roomType,
      counterpart,
      personaBlock: persona,
    });

    const transcript = history.messages.map((m) => `@${m.senderHandle}: ${m.content}`).join("\n");
    const userPrompt = [transcript && `# Conversation so far\n${transcript}`, promptTail]
      .filter(Boolean)
      .join("\n\n");

    const raw = await this.brain.complete(systemPrompt, userPrompt);
    return parseBrainOutput(raw);
  }

  /** Auto-reply to a counterpart agent's message. */
  private async answer(event: RoomMessageEvent): Promise<void> {
    console.log(`[loop] answering @${event.senderHandle} in room ${event.roomId} (${event.roomType})`);

    const output = await this.compose(
      event.roomId,
      event.roomType,
      {
        handle: event.senderHandle,
        type: event.senderAgentType,
        verificationLevel: event.senderVerificationLevel,
      },
      event.content,
      `# New message from @${event.senderHandle}\n${event.content}\n\nReply now as @${this.agentMeta.handle}, following the output format exactly.`
    );

    const result = await this.api.reply({
      roomId: event.roomId,
      inReplyToId: event.messageId,
      content: output.content,
      claims: output.claims,
      needsApproval: output.needs_approval,
    });

    this.queue.recordReply();
    console.log(
      `[loop] replied in room ${event.roomId}${result.requiresApproval ? " (승인 대기 — 웹에서 확인하세요)" : ""}`
    );
  }

  /** Execute an owner instruction: compose a message in the agent's voice and send it. */
  private async executeInstruction(event: RoomInstructionEvent): Promise<void> {
    console.log(`[loop] executing owner instruction in room ${event.roomId} (${event.roomType})`);
    try {
      const counterpart: CounterpartCard = event.counterpart
        ? {
            handle: event.counterpart.handle,
            type: event.counterpart.agentType,
            verificationLevel: event.counterpart.verificationLevel,
          }
        : { handle: "unknown", type: "personal", verificationLevel: "L0" };

      const output = await this.compose(
        event.roomId,
        event.roomType,
        counterpart,
        event.content,
        `# Instruction from your OWNER (not visible to the counterpart)\n${event.content}\n\nFollowing your owner's instruction, compose the message YOU will send to @${counterpart.handle}. Speak in your own voice as the owner's delegate — do not mention that you received an instruction. Follow the output format exactly.`
      );

      const result = await this.api.reply({
        roomId: event.roomId,
        instructionId: event.instructionId,
        content: output.content,
        claims: output.claims,
        needsApproval: output.needs_approval,
      });

      this.queue.recordReply();
      console.log(
        `[loop] instruction executed in room ${event.roomId}${result.requiresApproval ? " (승인 대기 — 웹에서 확인하세요)" : ""}`
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`[loop] instruction failed: ${message}`);
      await this.api.failInstruction(event.instructionId, message).catch(() => {});
    }
  }

  /** Drain pending messages + instructions accumulated while offline. */
  async drainInbox(): Promise<number> {
    const inbox = await this.api.inbox();
    this.syncSources(inbox.sources);
    for (const message of inbox.messages) {
      this.handleMessage(message);
    }
    for (const instruction of inbox.instructions ?? []) {
      this.handleInstruction(instruction);
    }
    return inbox.messages.length + (inbox.instructions?.length ?? 0);
  }

  // 같은 영수증이라도 상태가 바뀌면(confirmed→fulfilled→disputed) 다시 ingest하도록 상태까지 추적
  private ingestedReceipts = new Map<string, string>();

  /**
   * 거래 영수증을 OpenCrab(학습 메모리)에 ingest한다 (R3).
   * ocm_ 토큰이 없으면 no-op. 이미 같은 상태로 ingest한 건 건너뛴다.
   */
  async ingestReceipts(): Promise<number> {
    if (!this.opencrab) return 0; // ocm_ 미연결 — no-op
    const { receipts } = await this.api.receipts().catch(() => ({ receipts: [] }));
    let count = 0;
    for (const r of receipts) {
      if (this.ingestedReceipts.get(r.id) === r.status) continue;
      const ok = await this.opencrab.ingestReceipt(r);
      if (ok) {
        this.ingestedReceipts.set(r.id, r.status);
        count++;
      }
    }
    if (count > 0) console.log(`[loop] OpenCrab에 거래 이력 ${count}건 ingest`);
    return count;
  }
}
