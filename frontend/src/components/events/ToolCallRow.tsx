import { useState } from "react";
import type { PipelineEvent } from "../../api/types";

export default function ToolCallRow({ event, color }: { event: PipelineEvent; color: string }) {
  const [expanded, setExpanded] = useState(false);

  // ToolCallRow is only rendered for agent_tool_call events, but the
  // type system doesn't enforce that at call sites (AgentSpan.toolCalls
  // is PipelineEvent[]). Access fields safely via narrowing.
  if (event.event_type !== "agent_tool_call") return null;
  const d = event.data;

  return (
    <div className="text-[10px]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full text-left cursor-pointer bg-transparent border-none p-0 text-inherit"
      >
        <span className="font-mono font-medium" style={{ color }}>
          {d.tool}
        </span>
        <span className="text-text-dim truncate flex-1">
          {JSON.stringify(d.input || {}).slice(0, 60)}
        </span>
        <span className="text-text-dim">{expanded ? "-" : "+"}</span>
      </button>
      {expanded && (
        <div className="mt-1 ml-2 space-y-1 text-[10px] bg-bg/50 rounded p-2 border border-border-subtle">
          <div>
            <span className="text-text-dim">Input: </span>
            <pre className="inline text-text-muted whitespace-pre-wrap break-all">
              {JSON.stringify(d.input, null, 2)}
            </pre>
          </div>
          {d.result_snippet ? (
            <div>
              <span className="text-text-dim">Result: </span>
              <pre className="inline text-text-muted whitespace-pre-wrap break-all">
                {d.result_snippet}
              </pre>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
