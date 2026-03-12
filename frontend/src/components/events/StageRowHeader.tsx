import type { PipelineEventMap } from "../../api/types";
import type { StageInfo } from "../../utils/buildStageInfos";
import { formatTs } from "../../utils/buildStageInfos";
import { STAGE_LABEL } from "../../utils/stages";
import { STATUS_COLORS } from "../../utils/statusStyles";
import { formatDuration } from "../../utils/format";
import { CheckmarkIcon, FailIcon, PauseIcon } from "../shared/StatusIcons";

interface StageRowHeaderProps {
  info: StageInfo;
  isCurrent: boolean;
  isFailed: boolean;
  isPaused: boolean;
  isCompleted: boolean;
  expanded: boolean;
  color: string;
  onToggle: () => void;
}

export default function StageRowHeader({
  info,
  isCurrent,
  isFailed,
  isPaused,
  isCompleted,
  expanded,
  color,
  onToggle,
}: StageRowHeaderProps) {
  const duration =
    info.enteredAt && info.completedAt
      ? formatDuration(info.enteredAt, info.completedAt)
      : isCurrent
        ? "..."
        : "";

  const testRuns = info.events.filter((e): e is typeof e & { data: PipelineEventMap["test_run"] } => e.event_type === "test_run");
  const findings = info.events.filter((e) => e.event_type === "review_finding");

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 hover:bg-bg-card/50 transition-colors cursor-pointer rounded-lg"
      onClick={onToggle}
      aria-expanded={expanded}
      role="button"
    >
      {/* Status indicator */}
      <div className="flex-shrink-0">
        {isCompleted && !isCurrent ? (
          <CheckmarkIcon color={color} />
        ) : isFailed ? (
          <FailIcon />
        ) : isPaused ? (
          <PauseIcon />
        ) : isCurrent ? (
          <div
            className="w-4 h-4 rounded-full animate-pulse-glow"
            style={{ backgroundColor: `${color}40`, border: `1.5px solid ${color}` }}
          />
        ) : (
          <div className="w-4 h-4 rounded-full bg-bg-elevated border border-border-subtle" />
        )}
      </div>

      {/* Stage name */}
      <span
        className="text-xs font-medium min-w-[140px]"
        style={{ color: isFailed ? STATUS_COLORS.failed : isPaused ? STATUS_COLORS.paused : isCompleted || isCurrent ? color : STATUS_COLORS.inactive }}
      >
        {STAGE_LABEL[info.stage] || info.stage}
      </span>

      {/* Timing */}
      <div className="flex items-center gap-4 text-[10px] text-text-dim font-mono flex-1">
        {info.enteredAt && <span>{formatTs(info.enteredAt)}</span>}
        {info.enteredAt && info.completedAt && (
          <span className="text-text-dim">-</span>
        )}
        {info.completedAt && <span>{formatTs(info.completedAt)}</span>}
      </div>

      {/* Duration */}
      <span className="text-[11px] font-mono text-text-muted min-w-[50px] text-right">
        {duration}
      </span>

      {/* Summary badges */}
      <div className="flex items-center gap-2 min-w-[100px] justify-end">
        {info.agents.length > 0 && (
          <span className="text-[9px] bg-bg-elevated px-1.5 py-0.5 rounded text-text-dim">
            {info.agents.length} agent{info.agents.length !== 1 ? "s" : ""}
          </span>
        )}
        {testRuns.length > 0 && (
          <span
            className="text-[9px] px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: testRuns.some((t) => t.data.passed) ? "rgba(55,226,132,0.12)" : "rgba(255,65,87,0.12)",
              color: testRuns.some((t) => t.data.passed) ? "#37e284" : STATUS_COLORS.failed,
            }}
          >
            {testRuns.some((t) => t.data.passed) ? "PASS" : "FAIL"}
          </span>
        )}
        {findings.length > 0 && (
          <span className="text-[9px] bg-status-paused/12 text-status-paused px-1.5 py-0.5 rounded">
            {findings.length} finding{findings.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Expand toggle */}
      <span className="text-text-dim text-xs ml-1" aria-hidden="true">{expanded ? "-" : "+"}</span>
    </div>
  );
}
