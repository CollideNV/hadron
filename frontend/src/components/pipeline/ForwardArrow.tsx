import type { GroupColor } from "./stageTimelineConstants";

export default function ForwardArrow({
  filled,
  active,
  color,
}: {
  filled: boolean;
  active: boolean;
  color: GroupColor;
}) {
  const stroke = active
    ? color.accent
    : filled
      ? color.dim
      : "rgba(42, 63, 74, 0.8)";

  return (
    <div className="flex-shrink-0 self-start mt-[12px] mx-0.5">
      <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
        <line
          x1="0"
          y1="6"
          x2="14"
          y2="6"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          className={active ? "animate-flow-line" : undefined}
        />
        <polyline
          points="12,2 18,6 12,10"
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
