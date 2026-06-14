"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function ReviewButtons({ requestId }: { requestId: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function review(decision: "approved" | "rejected") {
    setLoading(true);
    await fetch(`/api/admin/verification/${requestId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    setLoading(false);
    router.refresh();
  }

  return (
    <div className="flex shrink-0 gap-2">
      <button className="pill pill-sunset pill-sm" onClick={() => review("approved")} disabled={loading}>
        승인
      </button>
      <button className="pill pill-sm" onClick={() => review("rejected")} disabled={loading}>
        반려
      </button>
    </div>
  );
}
