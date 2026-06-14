"use client";

import { useRouter } from "next/navigation";

export function MarkAllRead() {
  const router = useRouter();
  return (
    <button
      className="pill pill-sm"
      onClick={async () => {
        await fetch("/api/notifications", { method: "POST" });
        router.refresh();
      }}
    >
      모두 읽음
    </button>
  );
}
