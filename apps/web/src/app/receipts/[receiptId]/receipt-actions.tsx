"use client";

import { useState } from "react";

// 당사자가 영수증의 이행/분쟁을 기록한다. 결제 없음 — 사실 진술일 뿐.
export function ReceiptActions({ receiptId, status }: { receiptId: string; status: string }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  // disputed는 종착 상태 — 더 이상 액션 없음
  if (status === "disputed") return null;

  async function act(action: "fulfill" | "dispute") {
    setBusy(true);
    const res = await fetch(`/api/receipts/${receiptId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note: note.trim() || undefined }),
    });
    setBusy(false);
    if (res.ok) {
      window.location.reload();
    } else {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      alert(data.error ?? "처리에 실패했습니다.");
    }
  }

  return (
    <div className="card mt-4">
      <p className="eyebrow mb-3">이행 상태 업데이트</p>
      <textarea
        className="input"
        rows={2}
        placeholder="메모 / 분쟁 사유 (선택)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="mt-3 flex gap-2">
        {status === "confirmed" && (
          <button className="pill pill-sunset pill-sm" disabled={busy} onClick={() => act("fulfill")}>
            이행 완료로 표시
          </button>
        )}
        <button className="pill pill-sm" disabled={busy} onClick={() => act("dispute")}>
          분쟁 제기
        </button>
      </div>
      <p className="mt-2 text-xs text-mute">
        OpenCanal은 결제를 처리하지 않습니다. 이 기록은 양 당사자의 이행/분쟁 사실 진술입니다.
      </p>
    </div>
  );
}
