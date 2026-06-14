"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function PermissionsPanel({
  agentId,
  canNegotiate,
}: {
  agentId: string;
  canNegotiate: boolean;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function toggle() {
    setLoading(true);
    await fetch(`/api/agents/${agentId}/permissions`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ can_negotiate: !canNegotiate }),
    });
    setLoading(false);
    router.refresh();
  }

  return (
    <div className="card flex items-center justify-between bg-canvas-soft">
      <div>
        <p className="text-sm">협상 권한 (can_negotiate)</p>
        <p className="mt-1 text-xs text-mute">
          켜면 이 agent가 거래 룸을 열고 조건을 협상할 수 있습니다. 확정은 언제나 당신의 승인을
          거칩니다. 결제 권한(can_spend)은 제공되지 않습니다.
        </p>
      </div>
      <button
        className={`pill pill-sm ${canNegotiate ? "pill-sunset" : ""}`}
        onClick={toggle}
        disabled={loading}
      >
        {canNegotiate ? "켜짐" : "꺼짐"}
      </button>
    </div>
  );
}
