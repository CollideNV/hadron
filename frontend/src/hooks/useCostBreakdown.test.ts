import { renderHook } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useCostBreakdown } from "./useCostBreakdown";
import type { PipelineEvent } from "../api/types";

function makeAgentCompleted(
  stage: string,
  overrides: Record<string, unknown> = {},
): PipelineEvent {
  return {
    cr_id: "CR-1",
    event_type: "agent_completed",
    stage,
    timestamp: overrides.timestamp as number ?? Date.now() / 1000,
    data: {
      role: "test_role",
      repo: "test-repo",
      input_tokens: 1000,
      output_tokens: 200,
      cost_usd: 0.01,
      ...overrides,
    },
  } as PipelineEvent;
}

describe("useCostBreakdown", () => {
  it("returns empty breakdown for no events", () => {
    const { result } = renderHook(() => useCostBreakdown([]));
    expect(result.current.totalCostUsd).toBe(0);
    expect(result.current.byStage).toEqual([]);
    expect(result.current.byModel).toEqual([]);
    expect(result.current.timeline).toEqual([]);
  });

  it("aggregates cost by stage", () => {
    const events = [
      makeAgentCompleted("intake", { cost_usd: 0.002, timestamp: 1 }),
      makeAgentCompleted("implementation", { cost_usd: 0.05, timestamp: 2 }),
      makeAgentCompleted("implementation", { cost_usd: 0.03, timestamp: 3 }),
    ];

    const { result } = renderHook(() => useCostBreakdown(events));

    expect(result.current.totalCostUsd).toBeCloseTo(0.082);
    expect(result.current.byStage).toHaveLength(2);
    // Sorted by cost desc — implementation first
    expect(result.current.byStage[0].stage).toBe("implementation");
    expect(result.current.byStage[0].costUsd).toBeCloseTo(0.08);
    expect(result.current.byStage[0].agentCount).toBe(2);
    expect(result.current.byStage[1].stage).toBe("intake");
  });

  it("normalizes sub-stages (review:security_reviewer → review)", () => {
    const events = [
      makeAgentCompleted("review:security_reviewer", { cost_usd: 0.01, timestamp: 1 }),
      makeAgentCompleted("review:quality_reviewer", { cost_usd: 0.005, timestamp: 2 }),
    ];

    const { result } = renderHook(() => useCostBreakdown(events));

    expect(result.current.byStage).toHaveLength(1);
    expect(result.current.byStage[0].stage).toBe("review");
    expect(result.current.byStage[0].costUsd).toBeCloseTo(0.015);
    expect(result.current.byStage[0].agentCount).toBe(2);
  });

  it("aggregates cost by model from model_breakdown", () => {
    const events = [
      makeAgentCompleted("implementation", {
        cost_usd: 0.05,
        timestamp: 1,
        model: "claude-sonnet-4-20250514",
        model_breakdown: {
          "claude-sonnet-4-20250514": {
            input_tokens: 8000,
            output_tokens: 1500,
            cost_usd: 0.04,
            throttle_count: 0,
            throttle_seconds: 0,
            api_calls: 5,
          },
          "claude-haiku-4-5-20251001": {
            input_tokens: 2000,
            output_tokens: 300,
            cost_usd: 0.01,
            throttle_count: 0,
            throttle_seconds: 0,
            api_calls: 2,
          },
        },
      }),
    ];

    const { result } = renderHook(() => useCostBreakdown(events));

    expect(result.current.byModel).toHaveLength(2);
    expect(result.current.byModel[0].model).toBe("claude-sonnet-4-20250514");
    expect(result.current.byModel[0].costUsd).toBeCloseTo(0.04);
    expect(result.current.byModel[0].apiCalls).toBe(5);
    expect(result.current.byModel[1].model).toBe("claude-haiku-4-5-20251001");
  });

  it("falls back to single model when no breakdown", () => {
    const events = [
      makeAgentCompleted("intake", {
        cost_usd: 0.002,
        model: "claude-haiku-4-5-20251001",
        timestamp: 1,
      }),
    ];

    const { result } = renderHook(() => useCostBreakdown(events));

    expect(result.current.byModel).toHaveLength(1);
    expect(result.current.byModel[0].model).toBe("claude-haiku-4-5-20251001");
    expect(result.current.byModel[0].costUsd).toBeCloseTo(0.002);
    expect(result.current.byModel[0].apiCalls).toBe(1);
  });

  it("builds cumulative timeline", () => {
    const events = [
      makeAgentCompleted("intake", { cost_usd: 0.002, timestamp: 100 }),
      makeAgentCompleted("implementation", { cost_usd: 0.05, timestamp: 200 }),
      makeAgentCompleted("review:security_reviewer", { cost_usd: 0.01, timestamp: 300 }),
    ];

    const { result } = renderHook(() => useCostBreakdown(events));

    expect(result.current.timeline).toHaveLength(3);
    expect(result.current.timeline[0]).toEqual({ timestamp: 100, cumulativeCostUsd: 0.002 });
    expect(result.current.timeline[1].cumulativeCostUsd).toBeCloseTo(0.052);
    expect(result.current.timeline[2].cumulativeCostUsd).toBeCloseTo(0.062);
  });

  it("ignores non-agent_completed events", () => {
    const events: PipelineEvent[] = [
      {
        cr_id: "CR-1",
        event_type: "cost_update",
        stage: "intake",
        timestamp: 1,
        data: { total_cost_usd: 0.5 },
      } as PipelineEvent,
      makeAgentCompleted("intake", { cost_usd: 0.01, timestamp: 2 }),
    ];

    const { result } = renderHook(() => useCostBreakdown(events));

    expect(result.current.totalCostUsd).toBeCloseTo(0.01);
    expect(result.current.byStage).toHaveLength(1);
  });
});
