// WebSocket protocol between gateway <-> runner and gateway <-> browser.

import type { Claim } from "./schemas";

// ── Server → Runner ──

export interface RoomMessageEvent {
  type: "room.message";
  roomId: string;
  roomType: "question" | "discussion" | "trade" | "help";
  messageId: string;
  senderAgentId: string;
  senderHandle: string;
  senderAgentType: string;
  senderVerificationLevel: string;
  content: string;
  createdAt: string;
}

export interface ApprovalDecisionEvent {
  type: "approval.decision";
  messageId: string;
  approved: boolean;
}

// 소유자 → 자기 agent 지시. agent가 이를 해석해 상대에게 보낼 메시지를 작성한다.
export interface RoomInstructionEvent {
  type: "room.instruction";
  roomId: string;
  roomType: "question" | "discussion" | "trade" | "help";
  instructionId: string;
  content: string;
  counterpart: {
    agentId: string;
    handle: string;
    agentType: string;
    verificationLevel: string;
  } | null;
  createdAt: string;
}

export interface ServerHelloEvent {
  type: "hello";
  agentId: string;
  handle: string;
  pendingCount: number;
}

export type ServerEvent =
  | RoomMessageEvent
  | ApprovalDecisionEvent
  | ServerHelloEvent
  | RoomInstructionEvent;

// ── Runner → Server ──

export interface HeartbeatEvent {
  type: "heartbeat";
  busy: boolean;
}

export interface RunnerHelloEvent {
  type: "runner.hello";
  runnerVersion: string;
}

export type RunnerEvent = HeartbeatEvent | RunnerHelloEvent;

// ── Server → Browser ──

export interface BrowserRoomUpdateEvent {
  type: "room.update";
  roomId: string;
}

export interface BrowserPresenceEvent {
  type: "presence";
  agentId: string;
  status: "online" | "away" | "offline";
}

export type BrowserEvent = BrowserRoomUpdateEvent | BrowserPresenceEvent;

// ── Runner REST payloads ──

export interface AttestSourcePayload {
  packId: string;
  tenantId?: string;
  manifestHash?: string;
  nodeCount?: number;
  spaces?: string[];
}

// 러너가 OpenCrab(학습 메모리)에 ingest할 거래 영수증 요약. ocm_ 토큰이 있을 때만 사용된다.
export interface ReceiptIngest {
  id: string;
  roomId: string;
  roomType: "question" | "discussion" | "trade" | "help";
  status: "confirmed" | "fulfilled" | "disputed";
  terms: string;
  transcriptHash: string;
  counterpartHandle: string | null;
  proposerHandle: string;
  createdAt: string;
  fulfilledAt: string | null;
  disputedAt: string | null;
}

export interface RunnerReplyPayload {
  roomId: string;
  // 둘 중 하나: 상대 메시지에 대한 자동응답(inReplyToId) 또는 소유자 지시 수행(instructionId)
  inReplyToId?: string;
  instructionId?: string;
  content: string;
  claims?: Claim[];
  needsApproval: boolean;
}
