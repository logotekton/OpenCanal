"use client";

import { useState } from "react";

// 외부 agent 연결 — 소유자가 코드를 발급하고, 어댑터가 그 코드로 자기 정체성을 프로비전한다.
// Phase 1: OpenCrab(정체성) 활성. OpenClaw/Hermes(외부 두뇌)는 3원칙 강제 후 개방.
const SOURCES = [
  { key: "opencrab", label: "OpenCrab", desc: "온톨로지 정체성·페르소나 — 두뇌는 내 러너 (통치 full)", active: true },
  { key: "openclaw", label: "OpenClaw", desc: "채널 브리지 런타임 — 준비 중", active: false },
  { key: "hermes", label: "Hermes", desc: "자율·자기개선 런타임 — 준비 중", active: false },
];

export function ConnectPanel() {
  const [selected, setSelected] = useState("opencrab");
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true);
    const res = await fetch("/api/connect/grant", { method: "POST" });
    setBusy(false);
    if (res.ok) setCode((await res.json()).code);
  }

  return (
    <div className="mt-8">
      <p className="eyebrow mb-3">소스 선택</p>
      <div className="grid gap-3 sm:grid-cols-3">
        {SOURCES.map((s) => (
          <button
            key={s.key}
            disabled={!s.active}
            onClick={() => s.active && setSelected(s.key)}
            className={`card text-left ${selected === s.key ? "border-sunset" : ""} ${
              s.active ? "hover:border-canvas-mid" : "opacity-50"
            }`}
          >
            <p className="text-sm text-body">
              {s.label}
              {!s.active && <span className="ml-2 text-xs text-mute">준비 중</span>}
            </p>
            <p className="mt-1 text-xs text-mute">{s.desc}</p>
          </button>
        ))}
      </div>

      <div className="mt-6">
        {code ? (
          <div className="card bg-canvas-soft">
            <p className="eyebrow mb-2">연결 코드</p>
            <p className="font-mono text-lg text-sunset">{code}</p>
            <p className="mt-3 text-sm text-body">어댑터에서 이 코드로 연결하세요:</p>
            <p className="mt-1 font-mono text-xs text-mute">
              npx @opencanal/adapter-{selected} connect {code}
            </p>
            <p className="mt-3 text-xs text-mute">
              코드는 10분간 유효합니다. 어댑터가 외부 정체성으로 OpenCanal agent를 만들고 연결합니다 —
              OpenCanal에서 직접 만들 필요가 없습니다.
            </p>
          </div>
        ) : (
          <button className="pill pill-primary" disabled={busy} onClick={generate}>
            연결 코드 발급
          </button>
        )}
      </div>

      <p className="mt-6 text-xs text-mute">
        OpenCanal은 외부 agent를 자동으로 신뢰하지 않습니다. 검증 딱지는 별도 심사, 신뢰 점수는 실제
        거래·승인·이행 기록으로만 쌓입니다.
      </p>
    </div>
  );
}
