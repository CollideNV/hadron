import { useEffect, useRef } from "react";
import type { PipelineEvent } from "../../api/types";

/* ── Stage group colors (matching EventLog / StageTimeline) ── */
const STAGE_GROUP: Record<string, string> = {
  intake: "Understand",
  repo_id: "Understand",
  worktree_setup: "Understand",
  behaviour_translation: "Specify",
  behaviour_verification: "Specify",
  tdd: "Build",
  review: "Validate",
  rebase: "Validate",
  delivery: "Ship",
  release_gate: "Ship",
  release: "Ship",
  retrospective: "Ship",
};

const GROUP_ACCENT: Record<string, string> = {
  Understand: "#4dc9f6",
  Specify: "#a78bfa",
  Build: "#37e284",
  Validate: "#f0b832",
  Ship: "#f472b6",
};

function getStageColor(stageName: string): string {
  const baseStage = stageName.split(":")[0];
  const group = STAGE_GROUP[baseStage] || "Build";
  return GROUP_ACCENT[group] || "#37e284";
}

function summarize(event: PipelineEvent): string {
  const d = event.data;
  switch (event.event_type) {
    case "stage_entered":
      return `Entering ${event.stage}`;
    case "stage_completed":
      return `Completed ${event.stage}`;
    case "agent_started":
      return `Agent ${d.role} started${d.repo ? ` (${d.repo})` : ""}`;
    case "agent_completed":
      return `Agent ${d.role} completed${d.repo ? ` (${d.repo})` : ""}`;
    case "agent_tool_call":
      return `${d.role}: ${d.tool}(${JSON.stringify(d.input || {}).slice(0, 60)})`;
    case "test_run":
      return `Tests ${d.passed ? "PASSED" : "FAILED"} (iter ${d.iteration})`;
    case "review_finding":
      return `[${d.severity}] ${d.message || "finding"}`;
    case "cost_update":
      return `Cost: $${((d.total_cost_usd as number) || 0).toFixed(4)}`;
    case "pipeline_started":
      return "Pipeline started";
    case "pipeline_completed":
      return "Pipeline completed";
    case "pipeline_failed":
      return `Pipeline failed: ${d.error || ""}`;
    case "pipeline_paused":
      return "Pipeline paused for intervention";
    default:
      return event.event_type;
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface StageDetailLogProps {
  events: PipelineEvent[];
  stageName: string;
  onBack: () => void;
}

function badgeStyle(eventType: string, stageColor: string): React.CSSProperties {
  switch (eventType) {
    case "pipeline_failed":
    case "error":
      return { backgroundColor: "rgba(255, 65, 87, 0.15)", color: "#ff4157" };
    case "pipeline_paused":
      return { backgroundColor: "rgba(240, 184, 50, 0.15)", color: "#f0b832" };
    case "review_finding":
      return { backgroundColor: "rgba(240, 184, 50, 0.10)", color: "#f0b832" };
    case "pipeline_completed":
    case "stage_completed":
      return { backgroundColor: `${stageColor}18`, color: stageColor };
    case "test_run":
      return { backgroundColor: `${stageColor}18`, color: stageColor };
    case "cost_update":
    case "agent_tool_call":
      return { backgroundColor: "rgba(27, 40, 51, 0.8)", color: "#63717a" };
    default:
      return { backgroundColor: `${stageColor}15`, color: stageColor };
  }
}

export default function StageDetailLog({
  events,
  stageName,
  onBack,
}: StageDetailLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const stageColor = getStageColor(stageName);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border-subtle">
        <button
          onClick={onBack}
          className="text-[11px] text-text-dim hover:text-accent cursor-pointer bg-transparent border-none transition-colors"
        >
          &larr; All stages
        </button>
        <h3
          className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: stageColor }}
        >
          {stageName.replace(/_/g, " ")} Log
        </h3>
        <span className="text-[10px] text-text-dim ml-auto">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-0.5">
        {events.map((event, i) => (
          <div
            key={i}
            className="flex items-start gap-2 text-xs py-1 animate-fade-in"
          >
            <span className="text-text-dim font-mono whitespace-nowrap text-[10px]">
              {formatTime(event.timestamp)}
            </span>
            <span
              className="inline-flex px-1.5 py-0.5 rounded text-[9px] font-medium whitespace-nowrap"
              style={badgeStyle(event.event_type, stageColor)}
            >
              {event.event_type.replace(/_/g, " ")}
            </span>
            <span className="text-text-muted truncate">
              {summarize(event)}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
