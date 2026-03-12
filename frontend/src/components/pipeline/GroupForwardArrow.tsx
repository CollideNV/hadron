export default function GroupForwardArrow({ filled }: { filled: boolean }) {
  const stroke = filled
    ? "rgba(250, 249, 254, 0.15)"
    : "rgba(42, 63, 74, 0.5)";

  return (
    <div className="flex items-start self-end mb-6">
      <svg width="28" height="12" viewBox="0 0 28 12" fill="none">
        <line
          x1="0"
          y1="6"
          x2="20"
          y2="6"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
        />
        <polyline
          points="18,2 26,6 18,10"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </div>
  );
}
