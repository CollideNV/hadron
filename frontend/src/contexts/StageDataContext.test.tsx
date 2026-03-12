import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { StageDataProvider, useStageData } from "./StageDataContext";
import { makeEvent } from "../test-utils";
import type { PipelineEvent } from "../api/types";

function makeStageData(overrides: Partial<Parameters<typeof StageDataProvider>[0]> = {}) {
  const event = makeEvent({ event_type: "stage_entered" });
  return {
    crId: "cr-1",
    pipelineStatus: "running",
    events: [event] as PipelineEvent[],
    toolCalls: [] as PipelineEvent[],
    agentOutputs: [] as PipelineEvent[],
    agentNudges: [] as PipelineEvent[],
    testRuns: [] as PipelineEvent[],
    findings: [] as PipelineEvent[],
    ...overrides,
  };
}

describe("StageDataContext", () => {
  it("useStageData throws when used outside provider", () => {
    expect(() => {
      renderHook(() => useStageData());
    }).toThrow("useStageData must be used within StageDataProvider");
  });

  it("useStageData returns provided values within provider", () => {
    const data = makeStageData({ crId: "cr-42", pipelineStatus: "completed" });

    const { result } = renderHook(() => useStageData(), {
      wrapper: ({ children }) => (
        <StageDataProvider {...data}>{children}</StageDataProvider>
      ),
    });

    expect(result.current.crId).toBe("cr-42");
    expect(result.current.pipelineStatus).toBe("completed");
  });

  it("provider passes all fields correctly", () => {
    const toolCall = makeEvent({ event_type: "agent_tool_call" });
    const output = makeEvent({ event_type: "agent_output" });
    const nudge = makeEvent({ event_type: "agent_nudge" });
    const testRun = makeEvent({ event_type: "test_run" });
    const finding = makeEvent({ event_type: "review_finding" });
    const stageEvent = makeEvent({ event_type: "stage_entered" });

    const data = makeStageData({
      crId: "cr-99",
      pipelineStatus: "paused",
      events: [stageEvent],
      toolCalls: [toolCall],
      agentOutputs: [output],
      agentNudges: [nudge],
      testRuns: [testRun],
      findings: [finding],
    });

    const { result } = renderHook(() => useStageData(), {
      wrapper: ({ children }) => (
        <StageDataProvider {...data}>{children}</StageDataProvider>
      ),
    });

    expect(result.current.crId).toBe("cr-99");
    expect(result.current.pipelineStatus).toBe("paused");
    expect(result.current.events).toHaveLength(1);
    expect(result.current.toolCalls).toHaveLength(1);
    expect(result.current.agentOutputs).toHaveLength(1);
    expect(result.current.agentNudges).toHaveLength(1);
    expect(result.current.testRuns).toHaveLength(1);
    expect(result.current.findings).toHaveLength(1);
  });
});
