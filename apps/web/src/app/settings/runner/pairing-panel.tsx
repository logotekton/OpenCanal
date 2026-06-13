"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PresenceDot } from "@/components/presence";

interface AgentInfo {
  id: string;
  handle: string;
  displayName: string;
  status: string;
  device: { name: string | null; lastSeenAt: string | null; runnerVersion: string | null } | null;
}

export function PairingPanel({ agent, defaultOpen }: { agent: AgentInfo; defaultOpen?: boolean }) {
  const router = useRouter();
  const [code, setCode] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [open, setOpen] = useState(defaultOpen ?? false);
  const [loading, setLoading] = useState(false);

  async function generateCode() {
    setLoading(true);
    const res = await fetch(`/api/agents/${agent.id}/pairing`, { method: "POST" });
    setLoading(false);
    if (res.ok) {
      const data = await res.json();
      setCode(data.code);
      setExpiresAt(data.expiresAt);
    }
  }

  async function revokeDevice() {
    setLoading(true);
    await fetch(`/api/agents/${agent.id}/pairing`, { method: "DELETE" });
    setLoading(false);
    router.refresh();
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <PresenceDot status={agent.status} />
          <span className="text-lg">{agent.displayName}</span>
          <span className="font-mono text-sm text-mute">@{agent.handle}</span>
        </div>
        <button className="pill pill-sm" onClick={() => setOpen(!open)}>
          {open ? "접기" : "연결 관리"}
        </button>
      </div>

      {open && (
        <div className="mt-5 border-t border-hairline pt-5">
          {agent.device ? (
            <div className="flex items-center justify-between">
              <div className="text-sm text-body">
                <p>
                  연결된 러너: {agent.device.name ?? "이름 없음"}{" "}
                  {agent.device.runnerVersion && (
                    <span className="font-mono text-xs text-mute">v{agent.device.runnerVersion}</span>
                  )}
                </p>
                <p className="mt-1 text-mute">
                  마지막 접속:{" "}
                  {agent.device.lastSeenAt
                    ? new Date(agent.device.lastSeenAt).toLocaleString("ko-KR")
                    : "기록 없음"}
                </p>
              </div>
              <button className="pill pill-sm" onClick={revokeDevice} disabled={loading}>
                연결 해제
              </button>
            </div>
          ) : code ? (
            <div>
              <p className="text-sm text-body">터미널에서 아래 명령을 실행하고 코드를 입력하세요:</p>
              <pre className="mt-3 rounded-lg border border-hairline bg-canvas p-4 font-mono text-sm">
                npx opencanal-runner login
              </pre>
              <div className="mt-4 flex items-center gap-4">
                <span className="rounded-lg border border-sunset px-6 py-3 font-mono text-3xl tracking-[8px] text-sunset">
                  {code}
                </span>
                <span className="text-xs text-mute">
                  10분 내 만료
                  {expiresAt && ` (${new Date(expiresAt).toLocaleTimeString("ko-KR")})`}
                </span>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <p className="text-sm text-mute">
                러너를 연결하면 이 agent가 온라인 상태가 되고 자동으로 응답합니다.
              </p>
              <button className="pill pill-primary pill-sm" onClick={generateCode} disabled={loading}>
                페어링 코드 발급
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
