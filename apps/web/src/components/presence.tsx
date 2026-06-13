// 러너 하트비트 기반 presence 점 — 메신저 메타포 (online/away/offline)

const COLORS: Record<string, string> = {
  online: "#3ddc84",
  away: "#ffc285",
  offline: "#363a3f",
};

const LABELS: Record<string, string> = {
  online: "온라인 — 러너 연결됨",
  away: "자리비움 — 응답 지연 가능",
  offline: "오프라인 — 러너 재접속 시 응답",
};

export function PresenceDot({ status, size = 10 }: { status: string; size?: number }) {
  return (
    <span
      title={LABELS[status] ?? status}
      className="inline-block shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        backgroundColor: COLORS[status] ?? COLORS.offline,
        boxShadow: status === "online" ? `0 0 6px ${COLORS.online}` : "none",
      }}
    />
  );
}

export function PresenceLabel({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-mute">
      <PresenceDot status={status} />
      {status}
    </span>
  );
}
