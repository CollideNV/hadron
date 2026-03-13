import type { PipelineEvent } from "../../api/types";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import { getStageColor } from "../../utils/stages";
import { formatCost } from "../../utils/format";

function subStageLabel(stage: string): string {
  if (!stage.includes(":")) return stage;
  return stage.split(":")[1].replace(/_/g, " ");
}

function summarize(event: PipelineEvent): string {
  switch (event.event_type) {
    case "stage_entered":
      return event.stage.includes(":")
        ? `Entering ${subStageLabel(event.stage)}`
        : `Entering ${event.stage}`;
    case "stage_completed":
      return event.stage.includes(":")
        ? `Completed ${subStageLabel(event.stage)}`
        : `Completed ${event.stage}`;
    case "agent_started":
      return `Agent ${event.data.role} started${event.data.repo ? ` (${event.data.repo})` : ""}`;
    case "agent_completed":
      return `Agent ${event.data.role} completed${event.data.repo ? ` (${event.data.repo})` : ""}`;
    case "agent_tool_call":
      return `${event.data.role}: ${event.data.tool}(${JSON.stringify(event.data.input || {}).slice(0, 60)})`;
    case "test_run":
      return `Tests ${event.data.passed ? "PASSED" : "FAILED"} (iter ${event.data.iteration})`;
    case "review_finding":
      return `[${event.data.severity}] ${event.data.message || "finding"}`;
    case "cost_update":
      return `Cost: ${formatCost(event.data.total_cost_usd || 0)}`;
    case "pipeline_started":
      return "Pipeline started";
    case "pipeline_resumed":
      return "Pipeline resumed";
    case "pipeline_completed":
      return "Pipeline completed";
    case "pipeline_failed":
      return `Pipeline failed: ${event.data.error || ""}`;
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
  const { scrollRef, onScroll } = useAutoScroll<HTMLDivElement>([events.length]);
  const stageColor = getStageColor(stageName);

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
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-4 py-2 space-y-0.5">
        {events.map((event, i) => {
          const isSubStageHeader =
            event.event_type === "stage_entered" && event.stage.includes(":");

          return (
            <div key={i}>
              {isSubStageHeader && (
                <div
                  className="flex items-center gap-2 mt-3 mb-1 pt-2 border-t"
                  style={{ borderColor: `${stageColor}25` }}
                >
                  <span
                    className="w-1 h-3 rounded-full"
                    style={{ backgroundColor: stageColor }}
                  />
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: stageColor }}
                  >
                    {subStageLabel(event.stage)}
                  </span>
                </div>
              )}
              <div className="flex items-start gap-2 text-xs py-1 animate-fade-in">
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
            </div>
          );
        })}
        <div />
      </div>
    </div>
  );
}
