"use client";

import { useCallback, useEffect, useState } from "react";

interface Cap {
  key: string;
  label: string;
  description: string | null;
  requiresApproval: boolean;
  source: string;
}

// 소유자가 수동 capability를 추가/삭제한다. 어댑터 동기화 capability는 런타임 소관이라 표시만.
export function CapabilityEditor({ agentId }: { agentId: string }) {
  const [caps, setCaps] = useState<Cap[]>([]);
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`/api/agents/${agentId}/capabilities`, { cache: "no-store" });
    if (r.ok) setCaps((await r.json()).capabilities);
  }, [agentId]);
  useEffect(() => {
    load();
  }, [load]);

  async function add() {
    if (!key.trim() || !label.trim()) return;
    setBusy(true);
    const r = await fetch(`/api/agents/${agentId}/capabilities`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: key.trim(), label: label.trim(), description: desc.trim() || undefined }),
    });
    setBusy(false);
    if (r.ok) {
      setKey("");
      setLabel("");
      setDesc("");
      load();
    } else {
      const d = (await r.json().catch(() => ({}))) as { error?: string };
      alert(d.error ?? "추가에 실패했습니다.");
    }
  }

  async function remove(k: string) {
    await fetch(`/api/agents/${agentId}/capabilities`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: k }),
    });
    load();
  }

  const manual = caps.filter((c) => c.source === "manual");
  const adapter = caps.filter((c) => c.source === "adapter");

  return (
    <div className="card bg-canvas-soft">
      {manual.length === 0 && <p className="text-sm text-mute">수동으로 추가한 능력이 없습니다.</p>}
      {manual.map((c) => (
        <div key={c.key} className="flex items-center justify-between gap-2 py-1">
          <span className="text-sm text-body">
            {c.label} <span className="font-mono text-xs text-mute">{c.key}</span>
          </span>
          <button className="pill pill-sm" onClick={() => remove(c.key)}>
            삭제
          </button>
        </div>
      ))}
      {adapter.length > 0 && (
        <p className="mt-2 text-xs text-mute">
          어댑터 동기화: {adapter.map((c) => c.label).join(", ")} (런타임이 관리)
        </p>
      )}
      <div className="mt-3 flex flex-col gap-2">
        <div className="flex gap-2">
          <input
            className="input"
            style={{ flex: "0 0 34%" }}
            placeholder="key (예: code.review)"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <input
            className="input"
            placeholder="이름 (예: 코드 리뷰)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <input
            className="input"
            placeholder="설명 (선택)"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
          <button className="pill pill-sunset pill-sm" disabled={busy} onClick={add}>
            추가
          </button>
        </div>
      </div>
      <p className="mt-2 text-xs text-mute">추가한 능력은 모두 승인 봉투 안에서만 수행됩니다.</p>
    </div>
  );
}
