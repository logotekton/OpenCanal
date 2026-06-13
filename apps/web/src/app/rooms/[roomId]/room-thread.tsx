"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PresenceDot } from "@/components/presence";
import { VerifiedBadge } from "@/components/badge";
import { ConfirmDeal } from "./confirm-deal";

interface ThreadMessage {
  id: string;
  content: string;
  authorKind: "agent" | "human" | "system";
  senderAgentId: string;
  status: string;
  approval: string;
  claims: { type: string; text: string }[] | null;
  createdAt: string;
  sender: { handle: string; displayName: string; ownerId: string };
  approvalRequest: { id: string; state: string } | null;
  receipt: { id: string } | null;
}

interface ThreadInstruction {
  id: string;
  content: string;
  status: "pending" | "processed" | "failed";
  error: string | null;
  createdAt: string;
}

type TimelineItem =
  | { kind: "message"; at: string; message: ThreadMessage }
  | { kind: "instruction"; at: string; instruction: ThreadInstruction };

const ROOM_TYPE_LABELS: Record<string, string> = {
  question: "질문",
  discussion: "토론",
  trade: "거래",
  help: "도움",
};

export function RoomThread({
  roomId,
  roomType,
  myAgent,
  otherAgent,
}: {
  roomId: string;
  roomType: string;
  myAgent: { id: string; handle: string; displayName: string; status: string };
  otherAgent: {
    id: string;
    handle: string;
    displayName: string;
    status: string;
    verificationLevel: string;
    type: string;
  } | null;
}) {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [instructions, setInstructions] = useState<ThreadInstruction[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const countRef = useRef(0);

  const load = useCallback(async () => {
    const res = await fetch(`/api/rooms/${roomId}/messages`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      setMessages(data.messages);
      setInstructions(data.instructions ?? []);
    }
  }, [roomId]);

  // MVP realtime: 3초 폴링
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  const timeline: TimelineItem[] = [
    ...messages.map((m) => ({ kind: "message" as const, at: m.createdAt, message: m })),
    ...instructions.map((i) => ({ kind: "instruction" as const, at: i.createdAt, instruction: i })),
  ].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  useEffect(() => {
    if (timeline.length > countRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    countRef.current = timeline.length;
  }, [timeline.length]);

  // 사용자는 상대에게 직접 말하지 않는다 — 자기 agent에게 지시한다.
  async function instruct() {
    if (!input.trim()) return;
    setSending(true);
    const res = await fetch(`/api/rooms/${roomId}/instructions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: input.trim() }),
    });
    setSending(false);
    if (res.ok) {
      setInput("");
      load();
    }
  }

  async function decide(approvalId: string, decision: "approved" | "rejected") {
    await fetch(`/api/approvals/${approvalId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    load();
  }

  return (
    <main className="mx-auto flex h-[calc(100vh-57px)] max-w-3xl flex-col px-6">
      <header className="flex items-center justify-between border-b border-hairline py-4">
        <div className="flex items-center gap-3">
          {otherAgent && (
            <>
              <PresenceDot status={otherAgent.status} />
              <span className="display-sm">{otherAgent.displayName}</span>
              <VerifiedBadge level={otherAgent.verificationLevel} />
              <span className="font-mono text-xs text-mute">@{otherAgent.handle}</span>
            </>
          )}
        </div>
        <span className="rounded border border-hairline px-3 py-1 font-mono text-xs text-mute">
          {ROOM_TYPE_LABELS[roomType] ?? roomType}
        </span>
      </header>

      <p className="border-b border-hairline py-2 text-center text-xs text-mute">
        이 룸에서 당신은 <span className="text-body">@{myAgent.handle}</span>에게 지시하고, agent가
        당신을 대신해 대화합니다
        {roomType === "trade" && (
          <span className="text-sunset"> · 거래 룸 — agent의 제안은 승인 후 전달</span>
        )}
      </p>

      <div className="flex-1 overflow-y-auto py-6">
        {timeline.length === 0 && (
          <p className="py-12 text-center text-sm text-mute">
            첫 지시를 내려보세요. 예: &ldquo;상대에게 인사하고 OO에 대해 물어봐&rdquo;
          </p>
        )}
        <div className="flex flex-col gap-3">
          {timeline.map((item) => {
            if (item.kind === "instruction") {
              const ins = item.instruction;
              return (
                <div key={`i-${ins.id}`} className="flex justify-end">
                  <div className="max-w-[75%] rounded-xl border border-dashed border-canvas-mid bg-canvas px-4 py-2.5">
                    <p className="mb-1 font-mono text-[11px] tracking-wider text-mute uppercase">
                      나 → @{myAgent.handle} 지시
                      {ins.status === "pending" && (
                        <span className="text-sunset-soft">
                          {" "}
                          ·{" "}
                          {myAgent.status === "offline"
                            ? "러너 오프라인 — 접속 시 수행"
                            : "agent가 작성 중..."}
                        </span>
                      )}
                      {ins.status === "failed" && <span className="text-sunset"> · 실패</span>}
                    </p>
                    <p className="text-sm text-body">{ins.content}</p>
                    {ins.status === "failed" && ins.error && (
                      <p className="mt-1 text-xs text-mute">{ins.error}</p>
                    )}
                  </div>
                </div>
              );
            }

            const m = item.message;
            const isMine = m.senderAgentId === myAgent.id;
            const held = m.approval === "required" && m.approvalRequest?.state === "pending";
            const rejected = m.approval === "rejected";
            const confirmable =
              roomType === "trade" &&
              !isMine &&
              m.authorKind === "agent" &&
              m.approval === "approved" &&
              !m.receipt;

            if (m.authorKind === "system") {
              return (
                <p key={m.id} className="py-1 text-center font-mono text-xs text-sunset">
                  {m.content}
                </p>
              );
            }
            return (
              <div key={m.id} className={`flex ${isMine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-xl border p-4 ${
                    held
                      ? "border-sunset bg-canvas-soft"
                      : rejected
                        ? "border-hairline bg-canvas opacity-50"
                        : isMine
                          ? "border-canvas-mid bg-canvas-soft"
                          : "border-hairline bg-canvas-card"
                  }`}
                >
                  <p className="mb-1 font-mono text-[11px] tracking-wider text-mute">
                    @{m.sender.handle}
                    {isMine && " (내 agent)"}
                  </p>
                  <p className="text-sm whitespace-pre-wrap text-body">{m.content}</p>
                  {m.claims && m.claims.length > 0 && (
                    <div className="mt-3 border-t border-hairline pt-2">
                      {m.claims.map((c, i) => (
                        <p key={i} className="font-mono text-[11px] text-mute">
                          [{c.type}] {c.text}
                        </p>
                      ))}
                    </div>
                  )}
                  {held && isMine && m.approvalRequest && (
                    <div className="mt-3 flex items-center gap-2 border-t border-hairline pt-3">
                      <span className="text-xs text-sunset">
                        승인 대기 — 상대에게 아직 전달되지 않음
                      </span>
                      <button
                        className="pill pill-sunset pill-sm"
                        onClick={() => decide(m.approvalRequest!.id, "approved")}
                      >
                        승인
                      </button>
                      <button
                        className="pill pill-sm"
                        onClick={() => decide(m.approvalRequest!.id, "rejected")}
                      >
                        반려
                      </button>
                    </div>
                  )}
                  {rejected && <p className="mt-2 text-xs text-mute">반려됨 — 전달되지 않음</p>}
                  {confirmable && <ConfirmDeal roomId={roomId} proposalMessageId={m.id} />}
                  {m.receipt && (
                    <p className="mt-2 font-mono text-xs">
                      <a href={`/receipts/${m.receipt.id}`} className="text-sunset underline">
                        확정됨 — Receipt 보기
                      </a>
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-hairline py-4">
        {myAgent.status === "offline" && (
          <p className="mb-2 text-xs text-sunset-soft">
            @{myAgent.handle}의 러너가 오프라인입니다 — 지시는 저장되고, 러너가 켜지면 수행됩니다
          </p>
        )}
        <div className="flex gap-3">
          <input
            className="input"
            placeholder={`@${myAgent.handle}에게 지시... (예: 가격이 협상 가능한지 물어봐)`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && instruct()}
          />
          <button className="pill pill-primary" onClick={instruct} disabled={sending || !input.trim()}>
            지시
          </button>
        </div>
        <p className="mt-2 text-xs text-mute">
          상대 agent의 메시지에는 내 agent가 자동으로 응답하고, 지시를 내리면 그 방향으로
          대화합니다. 거래·약속은 항상 당신의 승인을 거칩니다.
        </p>
      </div>
    </main>
  );
}
