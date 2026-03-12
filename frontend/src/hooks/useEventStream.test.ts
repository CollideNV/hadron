import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useEventStream } from "./useEventStream";
import type { PipelineEvent } from "../api/types";
import { makeEvent } from "../test-utils";

// Capture the onEvent callback so we can fire events in tests
let capturedOnEvent: ((event: PipelineEvent) => void) | null = null;
const mockClose = vi.fn();

vi.mock("../api/sse", () => ({
  connectEventStream: vi.fn(
    (
      _crId: string,
      onEvent: (event: PipelineEvent) => void,
      _onError?: (err: Event) => void,
    ) => {
      capturedOnEvent = onEvent;
      return mockClose;
    },
  ),
}));

beforeEach(() => {
  capturedOnEvent = null;
  mockClose.mockClear();
});

describe("useEventStream", () => {
  it("starts with connecting status", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));
    expect(result.current.status).toBe("connecting");
    expect(result.current.events).toEqual([]);
  });

  it("returns initial state when crId is undefined", () => {
    const { result } = renderHook(() => useEventStream(undefined));
    expect(result.current.status).toBe("connecting");
    expect(capturedOnEvent).toBeNull();
  });

  it("transitions to running on pipeline_started", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(makeEvent({ event_type: "pipeline_started" }));
    });

    expect(result.current.status).toBe("running");
    expect(result.current.events).toHaveLength(1);
  });

  it("transitions to running on pipeline_resumed", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(makeEvent({ event_type: "pipeline_resumed" }));
    });

    expect(result.current.status).toBe("running");
  });

  it("transitions to completed on pipeline_completed", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(makeEvent({ event_type: "pipeline_completed" }));
    });

    expect(result.current.status).toBe("completed");
  });

  it("transitions to failed with error on pipeline_failed", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "pipeline_failed",
          data: { error: "OOM killed" },
        }),
      );
    });

    expect(result.current.status).toBe("failed");
    expect(result.current.error).toBe("OOM killed");
  });

  it("transitions to paused on pipeline_paused", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(makeEvent({ event_type: "pipeline_paused" }));
    });

    expect(result.current.status).toBe("paused");
  });

  it("updates currentStage on stage_entered", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "tdd" }),
      );
    });

    expect(result.current.currentStage).toBe("tdd");
    expect(result.current.status).toBe("running"); // auto-transitions from connecting
  });

  it("adds to completedStages on stage_completed", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({ event_type: "stage_completed", stage: "intake" }),
      );
    });

    expect(result.current.completedStages.has("intake")).toBe(true);
  });

  it("tracks tool calls", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "agent_tool_call",
          data: { tool: "read_file" },
        }),
      );
    });

    expect(result.current.toolCalls).toHaveLength(1);
    expect((result.current.toolCalls[0] as { data: { tool: string } }).data.tool).toBe("read_file");
  });

  it("tracks agent outputs", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "agent_output",
          data: { text: "analyzing code" },
        }),
      );
    });

    expect(result.current.agentOutputs).toHaveLength(1);
  });

  it("tracks agent nudges", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "agent_nudge",
          data: { text: "focus on tests" },
        }),
      );
    });

    expect(result.current.agentNudges).toHaveLength(1);
  });

  it("tracks test runs", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "test_run",
          data: { passed: true, iteration: 1 },
        }),
      );
    });

    expect(result.current.testRuns).toHaveLength(1);
  });

  it("tracks review findings", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "review_finding",
          data: { severity: "major" },
        }),
      );
    });

    expect(result.current.reviewFindings).toHaveLength(1);
  });

  it("updates cost on cost_update with total", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "cost_update",
          data: { total_cost_usd: 1.5 },
        }),
      );
    });

    expect(result.current.costUsd).toBe(1.5);
  });

  it("updates cost on cost_update with delta fallback", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "cost_update",
          data: { delta_usd: 0.25 },
        }),
      );
    });

    expect(result.current.costUsd).toBe(0.25);
  });

  it("sets error on error event", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "error",
          data: { message: "something broke" },
        }),
      );
    });

    expect(result.current.error).toBe("something broke");
  });

  it("closes connection on unmount", () => {
    const { unmount } = renderHook(() => useEventStream("cr-1"));
    unmount();
    expect(mockClose).toHaveBeenCalled();
  });

  it("deduplicates events with same type, stage, and timestamp", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 }),
      );
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 }),
      );
    });

    expect(result.current.events).toHaveLength(1);
  });

  it("does not deduplicate events with different timestamps", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 }),
      );
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 101 }),
      );
    });

    expect(result.current.events).toHaveLength(2);
  });

  it("handles cost_update with total_cost_usd=0", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    // First set some cost via delta
    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "cost_update",
          data: { delta_usd: 0.5 },
        }),
      );
    });
    expect(result.current.costUsd).toBe(0.5);

    // Now total_cost_usd=0 should override (not be falsy-skipped)
    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "cost_update",
          data: { total_cost_usd: 0 },
          timestamp: 1700000001,
        }),
      );
    });
    expect(result.current.costUsd).toBe(0);
  });

  it("handles cost_update with delta_usd only (accumulates)", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(
        makeEvent({
          event_type: "cost_update",
          data: { delta_usd: 0.1 },
          timestamp: 1700000001,
        }),
      );
      capturedOnEvent!(
        makeEvent({
          event_type: "cost_update",
          data: { delta_usd: 0.2 },
          timestamp: 1700000002,
        }),
      );
    });

    expect(result.current.costUsd).toBeCloseTo(0.3);
  });

  it("accumulates multiple events", () => {
    const { result } = renderHook(() => useEventStream("cr-1"));

    act(() => {
      capturedOnEvent!(makeEvent({ event_type: "pipeline_started" }));
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "intake" }),
      );
      capturedOnEvent!(
        makeEvent({ event_type: "stage_completed", stage: "intake" }),
      );
      capturedOnEvent!(
        makeEvent({ event_type: "stage_entered", stage: "tdd" }),
      );
    });

    expect(result.current.events).toHaveLength(4);
    expect(result.current.currentStage).toBe("tdd");
    expect(result.current.completedStages.has("intake")).toBe(true);
  });
});
