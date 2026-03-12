import { useState } from "react";
import type { AgentSpan } from "../../utils/buildStageInfos";
import { formatDuration } from "../../utils/format";
import ToolCallRow from "./ToolCallRow";

export default function AgentRow({ agent, color }: { agent: AgentSpan; color: string }) {
  const [expanded, setExpanded] = useState(false);
  const duration =
    agent.completedAt && agent.startedAt
      ? formatDuration(agent.startedAt, agent.completedAt)
      : "...";

  return (
    <div className="ml-4 border-l-2 pl-3 py-1" style={{ borderColor: `${color}30` }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left cursor-pointer bg-transparent border-none p-0 text-inherit"
      >
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{
            backgroundColor: agent.completedAt ? color : undefined,
            boxShadow: !agent.completedAt ? `0 0 6px ${color}` : undefined,
          }}
        />
        <span className="text-[11px] font-medium text-text">
          {agent.role}
        </span>
        {agent.repo && (
          <span className="text-[10px] text-text-dim font-mono">
            {agent.repo}
          </span>
        )}
        <span className="text-[10px] text-text-dim ml-auto">{duration}</span>
        {agent.toolCalls.length > 0 && (
          <span className="text-[10px] text-text-dim">
            {agent.toolCalls.length} tool{agent.toolCalls.length !== 1 ? "s" : ""}
          </span>
        )}
        <span className="text-[10px] text-text-dim">
          {expanded ? "-" : "+"}
        </span>
      </button>

      {expanded && agent.toolCalls.length > 0 && (
        <div className="mt-1.5 space-y-1 ml-3">
          {agent.toolCalls.map((tc, j) => (
            <ToolCallRow key={j} event={tc} color={color} />
          ))}
        </div>
      )}
    </div>
  );
}
