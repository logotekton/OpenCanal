"use client";

import { useState } from "react";
import { LODGING_TEMPLATE } from "@opencanal/shared";

interface Row {
  label: string;
  value: string;
}

// 거래 룸: 상대 agent의 승인된 제안을 확정한다. 선택적으로 구조화된 조건표(R4)를 동봉 —
// 숙박/예약 같은 vertical은 템플릿 라벨로 조건을 채운다. 결제는 없다(can_spend off).
export function ConfirmDeal({ roomId, proposalMessageId }: { roomId: string; proposalMessageId: string }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);

  function loadLodging() {
    setRows(LODGING_TEMPLATE.map((label) => ({ label, value: "" })));
  }
  function addRow() {
    setRows((r) => [...r, { label: "", value: "" }]);
  }
  function update(i: number, key: keyof Row, v: string) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [key]: v } : row)));
  }
  function remove(i: number) {
    setRows((r) => r.filter((_, idx) => idx !== i));
  }

  async function confirm() {
    setBusy(true);
    const conditions = rows
      .map((r) => ({ label: r.label.trim(), value: r.value.trim() }))
      .filter((r) => r.label);
    const res = await fetch(`/api/rooms/${roomId}/receipts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        proposalMessageId,
        conditions: conditions.length ? conditions : undefined,
      }),
    });
    setBusy(false);
    if (res.ok) {
      const { receiptId } = await res.json();
      window.location.href = `/receipts/${receiptId}`;
    } else {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      alert(data.error ?? "확정에 실패했습니다.");
    }
  }

  if (!open) {
    return (
      <div className="mt-3 border-t border-hairline pt-3">
        <button className="pill pill-sunset pill-sm" onClick={() => setOpen(true)}>
          이 제안 확정 — Receipt 생성
        </button>
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-hairline pt-3">
      <p className="mb-2 text-xs text-mute">합의 조건표 (선택) — 숙박/예약은 템플릿을 불러오세요</p>
      <div className="mb-2 flex flex-wrap gap-2">
        <button className="pill pill-sm" onClick={loadLodging}>
          숙박 조건 템플릿
        </button>
        <button className="pill pill-sm" onClick={addRow}>
          + 조건 추가
        </button>
      </div>
      {rows.length > 0 && (
        <div className="mb-3 flex flex-col gap-2">
          {rows.map((row, i) => (
            <div key={i} className="flex gap-2">
              <input
                className="input"
                style={{ flex: "0 0 38%" }}
                placeholder="항목 (예: 총 가격)"
                value={row.label}
                onChange={(e) => update(i, "label", e.target.value)}
              />
              <input
                className="input"
                placeholder="값 (예: 50,000원)"
                value={row.value}
                onChange={(e) => update(i, "value", e.target.value)}
              />
              <button className="pill pill-sm" onClick={() => remove(i)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <button className="pill pill-sunset pill-sm" disabled={busy} onClick={confirm}>
          {rows.some((r) => r.label.trim()) ? "이 조건으로 확정" : "조건 없이 확정"}
        </button>
        <button className="pill pill-sm" disabled={busy} onClick={() => setOpen(false)}>
          취소
        </button>
      </div>
    </div>
  );
}
