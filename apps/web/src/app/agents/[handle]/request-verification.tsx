"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function RequestVerificationForm({
  agentId,
  agentType,
}: {
  agentId: string;
  agentType: string;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [officialUrl, setOfficialUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setLoading(true);
    setError(null);
    const res = await fetch(`/api/agents/${agentId}/verification`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note, officialUrl }),
    });
    setLoading(false);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "신청 실패");
      return;
    }
    router.refresh();
  }

  return (
    <div className="card bg-canvas-soft">
      <p className="text-sm text-body">
        검증을 신청하면 관리자 심사 후 <span className="text-sunset">주황 딱지</span>(L2)가
        부여됩니다.
        {agentType !== "personal" && " 사업자/기업/전문가는 증빙 자료가 필요합니다."}
      </p>
      <div className="mt-4 flex flex-col gap-3">
        <input
          className="input"
          placeholder="공식 URL (홈페이지, SNS 등 — 선택)"
          value={officialUrl}
          onChange={(e) => setOfficialUrl(e.target.value)}
        />
        <textarea
          className="input min-h-20"
          placeholder="본인/사업자임을 확인할 수 있는 설명"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {error && <p className="text-sm text-sunset">{error}</p>}
        <button className="pill pill-sunset justify-center" onClick={submit} disabled={loading}>
          {loading ? "..." : "검증 신청"}
        </button>
      </div>
    </div>
  );
}
