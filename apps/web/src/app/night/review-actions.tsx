"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

// 아침 리뷰 액션: 승인 즉시, 반려는 사유 필수(팩 교정의 원료).
export function ReviewActions({ artifactId }: { artifactId: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<"idle" | "rejecting">("idle");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(decision: "approved" | "rejected") {
    if (decision === "rejected" && !reason.trim()) return;
    setBusy(true);
    const r = await fetch(`/api/night/artifacts/${artifactId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reason: decision === "rejected" ? reason.trim() : undefined }),
    });
    setBusy(false);
    if (r.ok) {
      router.refresh();
    } else {
      const d = (await r.json().catch(() => ({}))) as { error?: string };
      alert(d.error ?? "리뷰 처리에 실패했습니다.");
    }
  }

  if (mode === "rejecting") {
    return (
      <div className="mt-4 flex flex-col gap-2 border-t border-hairline pt-4">
        <textarea
          className="input"
          rows={3}
          placeholder="반려 사유"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          autoFocus
        />
        <p className="text-xs text-mute">사유가 팩 교정의 원료가 됩니다.</p>
        <div className="flex gap-2">
          <button
            className="pill pill-sunset pill-sm"
            disabled={busy || !reason.trim()}
            onClick={() => submit("rejected")}
          >
            반려 확정
          </button>
          <button className="pill pill-sm" disabled={busy} onClick={() => setMode("idle")}>
            취소
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 flex gap-2 border-t border-hairline pt-4">
      <button className="pill pill-primary pill-sm" disabled={busy} onClick={() => submit("approved")}>
        승인
      </button>
      <button className="pill pill-sm" disabled={busy} onClick={() => setMode("rejecting")}>
        반려
      </button>
    </div>
  );
}
