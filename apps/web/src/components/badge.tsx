// 주황 검증 딱지 — 인스타그램 verified 배지의 OpenCanal 버전 (L2 이상)

const LEVEL_ORDER = ["L0", "L1", "L2", "L3", "L4", "L5"];

export function isVerified(level: string): boolean {
  return LEVEL_ORDER.indexOf(level) >= LEVEL_ORDER.indexOf("L2");
}

export function VerifiedBadge({ level, size = 16 }: { level: string; size?: number }) {
  if (!isVerified(level)) return null;
  return (
    <span
      title={`Verified ${level}`}
      aria-label={`verified ${level}`}
      className="inline-flex shrink-0 items-center justify-center"
    >
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2l2.4 2.1 3.1-.5 1.1 3 3 1.1-.5 3.1L23.2 13l-2.1 2.4.5 3.1-3 1.1-1.1 3-3.1-.5L12 24l-2.4-2.1-3.1.5-1.1-3-3-1.1.5-3.1L.8 13l2.1-2.4-.5-3.1 3-1.1 1.1-3 3.1.5L12 2z"
          fill="#ff7a17"
          transform="translate(0 -1)"
        />
        <path
          d="M8.5 12.2l2.3 2.3 4.7-4.8"
          stroke="#0a0a0a"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

export function LevelChip({ level }: { level: string }) {
  const verified = isVerified(level);
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-xs tracking-wider ${
        verified ? "border-sunset text-sunset" : "border-hairline text-mute"
      }`}
    >
      {level}
    </span>
  );
}
