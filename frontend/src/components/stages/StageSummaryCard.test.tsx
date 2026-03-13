import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StageSummaryCard from "./StageSummaryCard";
import { makeEvent } from "../../test-utils";
import type { AgentSession } from "../agents/types";

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    role: "tdd_developer",
    repo: "",
    stage: "tdd",
    completed: false,
    items: [],
    inputTokens: 0,
    outputTokens: 0,
    costUsd: 0,
    roundCount: 0,
    throttleCount: 0,
    throttleSeconds: 0,
    modelBreakdown: {},
    loopIteration: 0,
    ...overrides,
  };
}

describe("StageSummaryCard", () => {
  it("shows stage name formatted (underscores to spaces)", () => {
    render(
      <StageSummaryCard
        stageName="behaviour_translation"
        events={[]}
        sessions={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("behaviour translation")).toBeInTheDocument();
  });

  it("shows duration when both entered and completed events present", () => {
    const events = [
      makeEvent({
        event_type: "stage_entered",
        stage: "tdd",
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "stage_completed",
        stage: "tdd",
        timestamp: 1700000075,
      }),
    ];
    render(
      <StageSummaryCard
        stageName="tdd"
        events={events}
        sessions={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("1m 15s")).toBeInTheDocument();
  });

  it("shows 'running...' when only entered event present", () => {
    const events = [
      makeEvent({
        event_type: "stage_entered",
        stage: "tdd",
        timestamp: 1700000000,
      }),
    ];
    render(
      <StageSummaryCard
        stageName="tdd"
        events={events}
        sessions={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("running...")).toBeInTheDocument();
  });

  it("hides duration when no stage events", () => {
    render(
      <StageSummaryCard
        stageName="tdd"
        events={[]}
        sessions={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.queryByText("Duration")).not.toBeInTheDocument();
  });

  it("shows total cost from sessions", () => {
    const sessions = [
      makeSession({ costUsd: 0.025 }),
      makeSession({ costUsd: 0.075 }),
    ];
    render(
      <StageSummaryCard
        stageName="tdd"
        events={[]}
        sessions={sessions}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("$0.100")).toBeInTheDocument();
  });

  it("shows test results summary (X passed, Y failed)", () => {
    const testRuns = [
      makeEvent({ event_type: "test_run", data: { passed: true } }),
      makeEvent({ event_type: "test_run", data: { passed: true } }),
      makeEvent({ event_type: "test_run", data: { passed: false } }),
    ];
    render(
      <StageSummaryCard
        stageName="tdd"
        events={[]}
        sessions={[]}
        testRuns={testRuns}
        findings={[]}
      />,
    );
    expect(screen.getByText("2 passed")).toBeInTheDocument();
    expect(screen.getByText("1 failed")).toBeInTheDocument();
  });

  it("shows finding severity counts", () => {
    const findings = [
      makeEvent({ event_type: "review_finding", data: { severity: "critical", message: "test" } }),
      makeEvent({ event_type: "review_finding", data: { severity: "critical", message: "test" } }),
      makeEvent({ event_type: "review_finding", data: { severity: "minor", message: "test" } }),
    ];
    render(
      <StageSummaryCard
        stageName="review"
        events={[]}
        sessions={[]}
        testRuns={[]}
        findings={findings}
      />,
    );
    expect(screen.getByText("2 critical")).toBeInTheDocument();
    expect(screen.getByText("1 minor")).toBeInTheDocument();
  });

  it("shows per-model cost breakdown from sessions", () => {
    const sessions = [
      makeSession({
        modelBreakdown: {
          "claude-3-5-sonnet-20241022": {
            input_tokens: 5000, output_tokens: 1000,
            cost_usd: 0.030, throttle_count: 0, throttle_seconds: 0, api_calls: 12,
          },
          "claude-3-5-haiku-20241022": {
            input_tokens: 2000, output_tokens: 500,
            cost_usd: 0.004, throttle_count: 1, throttle_seconds: 10, api_calls: 3,
          },
        },
      }),
    ];
    render(
      <StageSummaryCard
        stageName="tdd"
        events={[]}
        sessions={sessions}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("3-5-sonnet")).toBeInTheDocument();
    expect(screen.getByText("3-5-haiku")).toBeInTheDocument();
    expect(screen.getByText("Calls")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("$0.030")).toBeInTheDocument();
    expect(screen.getByText("$0.004")).toBeInTheDocument();
    expect(screen.getByText("Throttle")).toBeInTheDocument();
    expect(screen.getByText("10s")).toBeInTheDocument();
  });

  it("handles empty arrays for all props", () => {
    const { container } = render(
      <StageSummaryCard
        stageName="tdd"
        events={[]}
        sessions={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("tdd")).toBeInTheDocument();
    expect(screen.queryByText("Duration")).not.toBeInTheDocument();
    expect(screen.queryByText("Cost")).not.toBeInTheDocument();
    expect(screen.queryByText("Tests")).not.toBeInTheDocument();
    expect(screen.queryByText("Findings")).not.toBeInTheDocument();
    expect(container.querySelector(".rounded")).toBeFalsy;
  });
});
