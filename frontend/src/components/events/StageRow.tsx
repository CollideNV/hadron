import { useState } from "react";
import type { StageInfo } from "../../utils/buildStageInfos";
import { formatTs, summarizeEvent } from "../../utils/buildStageInfos";
import { STAGE_GROUP, GROUP_ACCENT, STAGE_LABEL } from "../../utils/stages";
import { STATUS_COLORS } from "../../utils/statusStyles";
import { formatDuration } from "../../utils/format";
import { CheckmarkIcon, FailIcon, PauseIcon } from "../shared/StatusIcons";
import AgentRow from "./AgentRow";
import EventBadge from "./EventBadge";

export default function StageRow({
  info,
  currentStage,
  status,
  onSelect,
}: {
  info: StageInfo;
  currentStage: string;
  status: string;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const group = STAGE_GROUP[info.stage] || "Ship";
  const color = GROUP_ACCENT[group] || "#37e284";
  const isCurrent = info.stage === currentStage;
  const isFailed = isCurrent && status === "failed";
  const isPaused = isCurrent && status === "paused";
  const isCompleted = info.completedAt !== null;

  const duration =
    info.enteredAt && info.completedAt
      ? formatDuration(info.enteredAt, info.completedAt)
      : isCurrent
        ? "..."
        : "";

  const testRuns = info.events.filter((e) => e.event_type === "test_run");
  const findings = info.events.filter((e) => e.event_type === "review_finding");

  return (
    <div className="animate-fade-in">
      <div
        className="flex items-center gap-3 px-4 py-2.5 hover:bg-bg-card/50 transition-colors cursor-pointer rounded-lg"
        onClick={() => setExpanded(!expanded)}
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

      {/* Expanded detail */}
      {expanded && (
        <div className="pb-2 space-y-1">
          {info.subStages.size > 0 ? (
            /* Render sub-stage grouped sections */
            Array.from(info.subStages.entries()).map(([key, sub]) => {
              const subDuration =
                sub.enteredAt && sub.completedAt
                  ? formatDuration(sub.enteredAt, sub.completedAt)
                  : sub.enteredAt
                    ? "..."
                    : "";
              return (
                <div key={key} className="ml-2">
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <span
                      className="w-1 h-4 rounded-full flex-shrink-0"
                      style={{ backgroundColor: sub.completedAt ? `${color}60` : color }}
                    />
                    <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color }}>
                      {key.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] text-text-dim font-mono ml-auto">
                      {subDuration}
                    </span>
                  </div>
                  {sub.agents.map((agent, i) => (
                    <AgentRow key={i} agent={agent} color={color} />
                  ))}
                </div>
              );
            })
          ) : (
            /* Flat agent list for stages without sub-stages */
            info.agents.map((agent, i) => (
              <AgentRow key={i} agent={agent} color={color} />
            ))
          )}

          {/* Show non-agent, non-stage events */}
          {info.events
            .filter(
              (e) =>
                e.event_type !== "stage_entered" &&
                e.event_type !== "stage_completed" &&
                e.event_type !== "agent_started" &&
                e.event_type !== "agent_completed" &&
                e.event_type !== "agent_tool_call",
            )
            .map((e, i) => (
              <div
                key={i}
                className="ml-4 pl-3 py-0.5 flex items-center gap-2 text-[10px]"
              >
                <span className="text-text-dim font-mono">
                  {formatTs(e.timestamp)}
                </span>
                <EventBadge type={e.event_type} />
                <span className="text-text-muted">{summarizeEvent(e)}</span>
              </div>
            ))}

          <button
            onClick={(ev) => {
              ev.stopPropagation();
              onSelect();
            }}
            className="ml-4 pl-3 text-[10px] bg-transparent border-none cursor-pointer transition-colors"
            style={{ color }}
          >
            View full log for this stage &rarr;
          </button>
        </div>
      )}
    </div>
  );
}
