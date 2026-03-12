import type { Stage } from "../../api/types";
import { STATUS_COLORS } from "../../utils/statusStyles";
import { STAGE_META, type GroupColor } from "./stageTimelineConstants";
import { SmallCheckmarkIcon, SmallFailIcon } from "../shared/StatusIcons";

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
            ? STATUS_COLORS.failedBg
            : isPaused
              ? STATUS_COLORS.pausedBg
              : isActive
                ? color.bg
                : STATUS_COLORS.inactiveBg,
          color: isFailed
            ? STATUS_COLORS.failed
            : isPaused
              ? STATUS_COLORS.paused
              : isActive
                ? color.accent
                : "#455560",
          borderWidth: "1px",
          borderStyle: "solid",
          borderColor: isFailed
            ? STATUS_COLORS.failedBorder
            : isPaused
              ? STATUS_COLORS.pausedBorder
              : isActive
                ? color.border
                : STATUS_COLORS.inactiveBorder,
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
          <SmallCheckmarkIcon />
        ) : isFailed ? (
          <SmallFailIcon />
        ) : (
          meta.icon
        )}
      </div>
      <span
        className="text-[10px] mt-1.5 text-center leading-tight transition-colors"
        style={{
          color: isFailed
            ? STATUS_COLORS.failed
            : isPaused
              ? STATUS_COLORS.paused
              : isActive || isSelected
                ? color.accent
                : STATUS_COLORS.inactive,
          fontWeight: isCurrent || isSelected ? 600 : 400,
        }}
      >
        {meta.label}
      </span>
    </button>
  );
}
