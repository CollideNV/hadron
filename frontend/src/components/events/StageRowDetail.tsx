import type { StageInfo } from "../../utils/buildStageInfos";
import { formatTs, summarizeEvent } from "../../utils/buildStageInfos";
import { formatDuration } from "../../utils/format";
import AgentRow from "./AgentRow";
import EventBadge from "./EventBadge";

interface StageRowDetailProps {
  info: StageInfo;
  color: string;
  onSelect: () => void;
}

export default function StageRowDetail({ info, color, onSelect }: StageRowDetailProps) {
  return (
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
  );
}
