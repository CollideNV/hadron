import type { Stage } from "../../api/types";
import { STAGE_META, type GroupColor } from "./stageTimelineConstants";

export default function StageNode({
  stage,
  isCompleted,
  isCurrent,
  isFailed,
  isPaused,
  isSelected,
  color,
  onClick,
}: {
  stage: Stage;
  isCompleted: boolean;
  isCurrent: boolean;
  isFailed: boolean;
  isPaused: boolean;
  isSelected: boolean;
  color: GroupColor;
  onClick: () => void;
}) {
  const meta = STAGE_META[stage];
  const isActive = isCompleted || isCurrent;

  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center bg-transparent border-none cursor-pointer p-0 group"
      title={`Filter to ${meta.label}`}
    >
      <div
        className={`w-9 h-9 rounded-lg flex items-center justify-center text-[10px] font-bold transition-all duration-300 relative ${
          isSelected ? "ring-2 ring-offset-1 ring-offset-[#0a2234] scale-110" : "group-hover:scale-105"
        }`}
        style={{
          backgroundColor: isFailed
            ? "rgba(255, 65, 87, 0.15)"
            : isPaused
              ? "rgba(240, 184, 50, 0.15)"
              : isActive
                ? color.bg
                : "rgba(27, 40, 51, 0.8)",
          color: isFailed
            ? "#ff4157"
            : isPaused
              ? "#f0b832"
              : isActive
                ? color.accent
                : "#455560",
          borderWidth: "1px",
          borderStyle: "solid",
          borderColor: isFailed
            ? "rgba(255, 65, 87, 0.3)"
            : isPaused
              ? "rgba(240, 184, 50, 0.3)"
              : isActive
                ? color.border
                : "rgba(42, 63, 74, 0.8)",
          boxShadow: isCurrent && !isFailed && !isPaused
            ? `0 0 8px ${color.dim}`
            : isSelected
              ? `0 0 6px ${color.dim}`
              : "none",
          ...(isSelected ? { ringColor: color.accent } : {}),
          animation: isCurrent && !isFailed && !isPaused ? "pulse-glow 2s ease-in-out infinite" : "none",
        }}
      >
        {isCompleted && !isCurrent ? (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-label="Completed">
            <path
              d="M3 7l3 3 5-5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : isFailed ? (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-label="Failed">
            <path
              d="M3 3l6 6M9 3l-6 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          meta.icon
        )}
      </div>
      <span
        className="text-[10px] mt-1.5 text-center leading-tight transition-colors"
        style={{
          color: isFailed
            ? "#ff4157"
            : isPaused
              ? "#f0b832"
              : isActive || isSelected
                ? color.accent
                : "#63717a",
          fontWeight: isCurrent || isSelected ? 600 : 400,
        }}
      >
        {meta.label}
      </span>
    </button>
  );
}
