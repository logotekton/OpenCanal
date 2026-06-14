"use client";

import { useState } from "react";

// 텔레그램 브리지 연결 — 소유자가 코드를 발급하고 봇에 `/pair <code>` 입력.
export function BridgePanel() {
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  async function generate() {
    setBusy(true);
    const res = await fetch("/api/bridge/pairing", { method: "POST" });
    setBusy(false);
    if (res.ok) setCode((await res.json()).code);
  }

  if (!open) {
    return (
      <button className="pill pill-sm" onClick={() => setOpen(true)}>
        텔레그램으로 받기
      </button>
    );
  }

  return (
    <div className="card mt-4 bg-canvas-soft">
      <p className="eyebrow mb-2">텔레그램 브리지</p>
      <p className="text-sm text-mute">
        승인 요청·거래 알림을 텔레그램에서 받고, 버튼으로 승인/반려할 수 있습니다.
      </p>
      {code ? (
        <div className="mt-3">
          <p className="text-sm">
            봇에게 다음을 보내세요: <code className="font-mono text-sunset">/pair {code}</code>
          </p>
          <p className="mt-1 text-xs text-mute">코드는 10분간 유효합니다.</p>
        </div>
      ) : (
        <button className="pill pill-sunset pill-sm mt-3" disabled={busy} onClick={generate}>
          연결 코드 발급
        </button>
      )}
    </div>
  );
}
