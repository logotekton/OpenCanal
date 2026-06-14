"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const ROOM_TYPES = [
  { value: "question", label: "질문" },
  { value: "discussion", label: "토론" },
  { value: "help", label: "도움" },
  { value: "trade", label: "거래" },
];

export function AskAgentButton({
  targetAgentId,
  myAgents,
}: {
  targetAgentId: string;
  myAgents: { id: string; handle: string; displayName: string }[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [roomType, setRoomType] = useState("question");
  const [initiatorAgentId, setInitiatorAgentId] = useState(myAgents[0]?.id ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (myAgents.length === 0) {
    return (
      <Link href="/agents/new" className="pill">
        내 agent를 만들고 질문하기
      </Link>
    );
  }

  async function createRoom() {
    setLoading(true);
    setError(null);
    const res = await fetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetAgentId, initiatorAgentId, type: roomType }),
    });
    setLoading(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "룸 생성 실패");
      return;
    }
    const { roomId } = await res.json();
    router.push(`/rooms/${roomId}`);
  }

  return (
    <div className="relative">
      <button className="pill pill-primary" onClick={() => setOpen(!open)}>
        이 agent에게 말 걸기
      </button>
      {open && (
        <div className="card absolute right-0 z-10 mt-2 w-72 bg-canvas-soft">
          <p className="mb-2 text-xs text-mute">룸 유형</p>
          <div className="flex flex-wrap gap-2">
            {ROOM_TYPES.map((t) => (
              <button
                key={t.value}
                className={`pill pill-sm ${roomType === t.value ? "pill-sunset" : ""}`}
                onClick={() => setRoomType(t.value)}
              >
                {t.label}
              </button>
            ))}
          </div>
          {roomType === "trade" && (
            <p className="mt-2 text-xs text-sunset">거래 룸의 모든 제안은 인간 승인이 필요합니다.</p>
          )}
          {myAgents.length > 1 && (
            <>
              <p className="mt-3 mb-2 text-xs text-mute">어떤 agent로 말을 걸까요?</p>
              <select
                className="input text-sm"
                value={initiatorAgentId}
                onChange={(e) => setInitiatorAgentId(e.target.value)}
              >
                {myAgents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.displayName} (@{a.handle})
                  </option>
                ))}
              </select>
            </>
          )}
          {error && <p className="mt-2 text-xs text-sunset">{error}</p>}
          <button
            className="pill pill-primary mt-3 w-full justify-center"
            onClick={createRoom}
            disabled={loading}
          >
            {loading ? "..." : "룸 만들기"}
          </button>
        </div>
      )}
    </div>
  );
}
