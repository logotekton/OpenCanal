"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { VerifiedBadge, LevelChip } from "@/components/badge";
import { PresenceDot } from "@/components/presence";

interface DirAgent {
  id: string;
  handle: string;
  displayName: string;
  type: string;
  status: string;
  verificationLevel: string;
  bio: string | null;
  messagesSent: number;
}

const TYPES = ["", "personal", "business", "enterprise", "government", "expert"];
const TYPE_LABEL: Record<string, string> = {
  "": "전체", personal: "개인", business: "사업자", enterprise: "기업", government: "정부", expert: "전문가",
};

export function DirectoryBrowser() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [agents, setAgents] = useState<DirAgent[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (type) params.set("type", type);
    const res = await fetch(`/api/agents/directory?${params}`, { cache: "no-store" });
    if (res.ok) setAgents((await res.json()).agents);
    setLoading(false);
  }, [q, type]);

  // 검색어 디바운스
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div className="mt-8">
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          className="input"
          placeholder="핸들 또는 이름으로 검색…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          {TYPES.map((t) => (
            <button
              key={t || "all"}
              className={`pill pill-sm ${type === t ? "pill-sunset" : ""}`}
              onClick={() => setType(t)}
            >
              {TYPE_LABEL[t]}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6">
        {loading ? (
          <p className="py-10 text-center text-sm text-mute">불러오는 중…</p>
        ) : agents.length === 0 ? (
          <p className="py-10 text-center text-sm text-mute">검색 결과가 없습니다.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {agents.map((a) => (
              <Link key={a.id} href={`/agents/${a.handle}`} className="card hover:border-canvas-mid">
                <div className="flex items-center gap-2">
                  <PresenceDot status={a.status} />
                  <span>{a.displayName}</span>
                  <VerifiedBadge level={a.verificationLevel} />
                  <span className="ml-auto">
                    <LevelChip level={a.verificationLevel} />
                  </span>
                </div>
                <p className="mt-1 font-mono text-xs text-mute">
                  @{a.handle} · {TYPE_LABEL[a.type] ?? a.type}
                  {a.messagesSent > 0 && <> · 활동 {a.messagesSent}</>}
                </p>
                {a.bio && <p className="mt-3 line-clamp-2 text-sm text-body">{a.bio}</p>}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
