import { useEffect, useRef, useCallback, useState } from "react";
import { connectEventStream } from "../api/sse";
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

const INITIAL_STATE: EventStreamState = {
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

export function useEventStream(crId: string | undefined): EventStreamState {
  const [state, setState] = useState<EventStreamState>(INITIAL_STATE);
  const closeRef = useRef<(() => void) | null>(null);

  const handleEvent = useCallback((event: PipelineEvent) => {
    setState((prev) => {
      const events = [...prev.events, event];
      let {
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
      } = prev;

      // Clone mutable collections
      completedStages = new Set(completedStages);
      stageData = new Map(stageData);

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
          error = (event.data.error as string) || "Pipeline failed";
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
          costUsd = (event.data.total_cost_usd as number) || costUsd + ((event.data.delta_usd as number) || 0);
          break;
        case "error":
          error = (event.data.message as string) || "Unknown error";
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
    });
  }, []);

  useEffect(() => {
    if (!crId) return;

    setState(INITIAL_STATE);

    const close = connectEventStream(crId, handleEvent, () => {
      // On SSE error, if we haven't received a terminal event, mark as potentially done
      // (the server closes the connection on completion)
    });
    closeRef.current = close;

    return () => {
      close();
      closeRef.current = null;
    };
  }, [crId, handleEvent]);

  return state;
}
