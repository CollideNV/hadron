import type { PipelineEvent } from "../api/types";

export interface EventStreamState {
  events: PipelineEvent[];
  currentStage: string;
  completedStages: Set<string>;
  stageData: Map<string, unknown>;
  toolCalls: PipelineEvent[];
  agentOutputs: PipelineEvent[];
  agentNudges: PipelineEvent[];
  testRuns: PipelineEvent[];
  reviewFindings: PipelineEvent[];
  costUsd: number;
  status: "connecting" | "running" | "completed" | "failed" | "paused";
  error: string | null;
}

export const INITIAL_STATE: EventStreamState = {
  events: [],
  currentStage: "",
  completedStages: new Set(),
  stageData: new Map(),
  toolCalls: [],
  agentOutputs: [],
  agentNudges: [],
  testRuns: [],
  reviewFindings: [],
  costUsd: 0,
  status: "connecting",
  error: null,
};

/**
 * Pure function that computes the next EventStreamState given the previous
 * state and a new PipelineEvent.  Extracted from useEventStream so it can
 * be tested independently of React.
 */
export function reduceEvent(
  prev: EventStreamState,
  event: PipelineEvent,
): EventStreamState {
  const events = [...prev.events, event];
  let {
    currentStage,
    toolCalls,
    agentOutputs,
    agentNudges,
    testRuns,
    reviewFindings,
    costUsd,
    status,
    error,
  } = prev;

  // Clone mutable collections
  const completedStages = new Set(prev.completedStages);
  const stageData = new Map(prev.stageData);

  switch (event.event_type) {
    case "pipeline_started":
    case "pipeline_resumed":
      status = "running";
      break;
    case "pipeline_completed":
      status = "completed";
      break;
    case "pipeline_failed":
      status = "failed";
      error = event.data.error || "Pipeline failed";
      break;
    case "pipeline_paused":
      status = "paused";
      break;
    case "stage_entered":
      currentStage = event.stage;
      if (status === "connecting") status = "running";
      break;
    case "stage_completed":
      completedStages.add(event.stage);
      stageData.set(event.stage, event.data);
      break;
    case "agent_tool_call":
      toolCalls = [...toolCalls, event];
      break;
    case "agent_output":
      agentOutputs = [...agentOutputs, event];
      break;
    case "agent_nudge":
      agentNudges = [...agentNudges, event];
      break;
    case "test_run":
      testRuns = [...testRuns, event];
      break;
    case "review_finding":
      reviewFindings = [...reviewFindings, event];
      break;
    case "cost_update":
      if (typeof event.data.total_cost_usd === "number") {
        costUsd = event.data.total_cost_usd;
      } else if (typeof event.data.delta_usd === "number") {
        costUsd = prev.costUsd + event.data.delta_usd;
      }
      break;
    case "error":
      error = event.data.message || "Unknown error";
      break;
  }

  return {
    events,
    currentStage,
    completedStages,
    stageData,
    toolCalls,
    agentOutputs,
    agentNudges,
    testRuns,
    reviewFindings,
    costUsd,
    status,
    error,
  };
}
