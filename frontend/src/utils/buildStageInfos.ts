import type { PipelineEvent } from "../api/types";
import { STAGES } from "../api/types";
import { formatCost } from "./format";

/* ── Types ── */
export interface SubStageInfo {
  label: string;
  enteredAt: number | null;
  completedAt: number | null;
  agents: AgentSpan[];
}

export interface StageInfo {
  stage: string;
  enteredAt: number | null;
  completedAt: number | null;
  events: PipelineEvent[];
  agents: AgentSpan[];
  subStages: Map<string, SubStageInfo>;
}

export interface AgentSpan {
  role: string;
  repo: string;
  startedAt: number;
  completedAt: number | null;
  toolCalls: PipelineEvent[];
}

/* ── Helpers ── */
export function getOrCreateSubStage(info: StageInfo, subKey: string): SubStageInfo {
  let sub = info.subStages.get(subKey);
  if (!sub) {
    sub = { label: subKey, enteredAt: null, completedAt: null, agents: [] };
    info.subStages.set(subKey, sub);
  }
  return sub;
}

export function buildStageInfos(events: PipelineEvent[]): StageInfo[] {
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
          role: e.data.role || "agent",
          repo: e.data.repo || "",
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

export function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function summarizeEvent(event: PipelineEvent): string {
  switch (event.event_type) {
    case "test_run":
      return `Tests ${event.data.passed ? "PASSED" : "FAILED"} (iteration ${event.data.iteration})`;
    case "review_finding":
      return `[${event.data.severity}] ${event.data.message || "finding"}${event.data.file ? ` @ ${event.data.file}` : ""}`;
    case "cost_update":
      return formatCost(event.data.total_cost_usd || 0);
    case "intervention_set":
      return "Intervention received";
    case "error":
      return String(event.data.message || event.data.error || "Error");
    default:
      return event.event_type;
  }
}
