import { useState } from "react";
import type { PipelineEvent } from "../../api/types";
import { STAGES } from "../../api/types";

/* ── Group colors (same as StageTimeline) ── */
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

const STAGE_LABEL: Record<string, string> = {
  intake: "Intake",
  repo_id: "Repo ID",
  worktree_setup: "Worktree Setup",
  behaviour_translation: "Behaviour Translation",
  behaviour_verification: "Behaviour Verification",
  tdd: "TDD Development",
  review: "Code Review",
  rebase: "Rebase",
  delivery: "Delivery",
  release_gate: "Release Gate",
  release: "Release",
  retrospective: "Retrospective",
};

/* ── Types ── */
interface SubStageInfo {
  label: string;
  enteredAt: number | null;
  completedAt: number | null;
  agents: AgentSpan[];
}

interface StageInfo {
  stage: string;
  enteredAt: number | null;
  completedAt: number | null;
  events: PipelineEvent[];
  agents: AgentSpan[];
  subStages: Map<string, SubStageInfo>;
}

interface AgentSpan {
  role: string;
  repo: string;
  startedAt: number;
  completedAt: number | null;
  toolCalls: PipelineEvent[];
}

/* ── Helpers ── */
function getOrCreateSubStage(info: StageInfo, subKey: string): SubStageInfo {
  let sub = info.subStages.get(subKey);
  if (!sub) {
    sub = { label: subKey, enteredAt: null, completedAt: null, agents: [] };
    info.subStages.set(subKey, sub);
  }
  return sub;
}

function buildStageInfos(events: PipelineEvent[]): StageInfo[] {
  const map = new Map<string, StageInfo>();

  // Pre-create entries in pipeline order so they appear sorted
  for (const s of STAGES) {
    map.set(s, {
      stage: s,
      enteredAt: null,
      completedAt: null,
      events: [],
      agents: [],
      subStages: new Map(),
    });
  }

  // Track current agent per sub-stage (or base stage) for concurrent reviewers
  const agentByKey = new Map<string, AgentSpan>();

  for (const e of events) {
    // Normalize stage key — strip ":sub_stage" suffixes
    const baseStage = e.stage.split(":")[0];
    const subKey = e.stage.includes(":") ? e.stage.split(":")[1] : null;
    const info = map.get(baseStage);
    if (!info) continue;

    info.events.push(e);

    switch (e.event_type) {
      case "stage_entered":
        if (subKey) {
          const sub = getOrCreateSubStage(info, subKey);
          sub.enteredAt ??= e.timestamp;
        } else {
          info.enteredAt ??= e.timestamp;
        }
        break;
      case "stage_completed":
        if (subKey) {
          const sub = getOrCreateSubStage(info, subKey);
          sub.completedAt = e.timestamp;
        } else {
          info.completedAt = e.timestamp;
        }
        break;
      case "agent_started": {
        const agentTrackKey = subKey || `${baseStage}:${e.data.role}:${e.data.repo}`;
        const agent: AgentSpan = {
          role: (e.data.role as string) || "agent",
          repo: (e.data.repo as string) || "",
          startedAt: e.timestamp,
          completedAt: null,
          toolCalls: [],
        };
        agentByKey.set(agentTrackKey, agent);
        if (subKey) {
          getOrCreateSubStage(info, subKey).agents.push(agent);
        } else {
          info.agents.push(agent);
        }
        break;
      }
      case "agent_completed": {
        const agentTrackKey = subKey || `${baseStage}:${e.data.role}:${e.data.repo}`;
        const tracked = agentByKey.get(agentTrackKey);
        if (tracked) tracked.completedAt = e.timestamp;
        agentByKey.delete(agentTrackKey);
        break;
      }
      case "agent_tool_call": {
        const agentTrackKey = subKey || `${baseStage}:${e.data.role}:${e.data.repo}`;
        const tracked = agentByKey.get(agentTrackKey);
        if (tracked) tracked.toolCalls.push(e);
        break;
      }
    }
  }

  // Only return stages that actually appeared
  return Array.from(map.values()).filter(
    (s) => s.enteredAt !== null || s.events.length > 0,
  );
}

function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(start: number, end: number): string {
  const secs = Math.round(end - start);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return `${mins}m ${rem}s`;
}

/* ── Sub-components ── */
function AgentRow({ agent, color }: { agent: AgentSpan; color: string }) {
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

function ToolCallRow({ event, color }: { event: PipelineEvent; color: string }) {
  const [expanded, setExpanded] = useState(false);
  const d = event.data;

  return (
    <div className="text-[10px]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full text-left cursor-pointer bg-transparent border-none p-0 text-inherit"
      >
        <span className="font-mono font-medium" style={{ color }}>
          {String(d.tool)}
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
                {String(d.result_snippet)}
              </pre>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function StageRow({
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
      >
        {/* Status indicator */}
        <div className="flex-shrink-0">
          {isCompleted && !isCurrent ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" stroke={color} strokeWidth="1.5" opacity="0.4" />
              <path d="M5 8l2 2 4-4" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : isFailed ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" stroke="#ff4157" strokeWidth="1.5" opacity="0.4" />
              <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="#ff4157" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          ) : isPaused ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" stroke="#f0b832" strokeWidth="1.5" opacity="0.4" />
              <rect x="6" y="5" width="1.5" height="6" rx="0.5" fill="#f0b832" />
              <rect x="8.5" y="5" width="1.5" height="6" rx="0.5" fill="#f0b832" />
            </svg>
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
          style={{ color: isFailed ? "#ff4157" : isPaused ? "#f0b832" : isCompleted || isCurrent ? color : "#63717a" }}
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
                color: testRuns.some((t) => t.data.passed) ? "#37e284" : "#ff4157",
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
        <span className="text-text-dim text-xs ml-1">{expanded ? "-" : "+"}</span>
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

function EventBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    test_run: "bg-accent/10 text-accent/80",
    review_finding: "bg-status-paused/10 text-status-paused",
    cost_update: "bg-bg-elevated text-text-dim",
    error: "bg-status-failed/15 text-status-failed",
  };
  return (
    <span
      className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-medium whitespace-nowrap ${styles[type] || "bg-bg-elevated text-text-dim"}`}
    >
      {type.replace(/_/g, " ")}
    </span>
  );
}

function summarizeEvent(event: PipelineEvent): string {
  const d = event.data;
  switch (event.event_type) {
    case "test_run":
      return `Tests ${d.passed ? "PASSED" : "FAILED"} (iteration ${d.iteration})`;
    case "review_finding":
      return `[${d.severity}] ${d.message || "finding"}${d.file ? ` @ ${d.file}` : ""}`;
    case "cost_update":
      return `$${((d.total_cost_usd as number) || 0).toFixed(4)}`;
    case "intervention_set":
      return "Intervention received";
    case "error":
      return String(d.message || d.error || "Error");
    default:
      return event.event_type;
  }
}

/* ── Main component ── */
interface EventLogProps {
  events: PipelineEvent[];
  currentStage?: string;
  status?: string;
  onSelectStage?: (stage: string) => void;
}

export default function EventLog({
  events,
  currentStage = "",
  status = "",
  onSelectStage,
}: EventLogProps) {
  const stages = buildStageInfos(events);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-subtle">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Pipeline Stages
        </h3>
        <span className="text-[10px] text-text-dim">
          {stages.length} stage{stages.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {stages.length === 0 && (
          <p className="text-xs text-text-dim py-8 text-center">
            Waiting for events...
          </p>
        )}
        {stages.map((info) => (
          <StageRow
            key={info.stage}
            info={info}
            currentStage={currentStage}
            status={status}
            onSelect={() => onSelectStage?.(info.stage)}
          />
        ))}
      </div>
    </div>
  );
}
