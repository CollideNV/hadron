import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import StageDetailView from "./StageDetailView";
import { StageDataProvider } from "../../contexts/StageDataContext";
import { makeEvent } from "../../test-utils";
import type { PipelineEvent } from "../../api/types";

vi.mock("../../api/client", () => ({
  sendNudge: vi.fn().mockResolvedValue({ status: "nudge_set" }),
}));

function renderWithContext(
  props: { stageName: string; onBack: () => void },
  contextOverrides: Partial<{
    crId: string;
    pipelineStatus: string;
    events: PipelineEvent[];
    toolCalls: PipelineEvent[];
    agentOutputs: PipelineEvent[];
    agentNudges: PipelineEvent[];
    testRuns: PipelineEvent[];
    findings: PipelineEvent[];
  }> = {},
) {
  const contextDefaults = {
    crId: "cr-1",
    pipelineStatus: "running",
    events: [],
    toolCalls: [],
    agentOutputs: [],
    agentNudges: [],
    testRuns: [],
    findings: [],
    ...contextOverrides,
  };
  return render(
    <StageDataProvider {...contextDefaults}>
      <StageDetailView {...props} />
    </StageDataProvider>,
  );
}

describe("StageDetailView", () => {
  it("shows stage name and back button", () => {
    renderWithContext({ stageName: "tdd", onBack: vi.fn() });
    const tddLabels = screen.getAllByText("tdd");
    expect(tddLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/back/i)).toBeInTheDocument();
  });

  it("calls onBack when back button clicked", () => {
    const onBack = vi.fn();
    renderWithContext({ stageName: "tdd", onBack });
    fireEvent.click(screen.getByText(/back/i));
    expect(onBack).toHaveBeenCalled();
  });

  it("shows 'no agent sessions' when no activity", () => {
    renderWithContext({ stageName: "tdd", onBack: vi.fn() });
    expect(screen.getByText(/no agent sessions/i)).toBeInTheDocument();
  });

  it("shows agent session in sidebar and conversation", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "backend" },
      }),
    ];
    const agentOutputs = [
      makeEvent({
        event_type: "agent_output",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "backend", text: "Writing tests now" },
      }),
    ];
    renderWithContext(
      { stageName: "tdd", onBack: vi.fn() },
      { events, agentOutputs },
    );
    const devLabels = screen.getAllByText("tdd developer");
    expect(devLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Writing tests now")).toBeInTheDocument();
  });

  it("shows summary card with test results", () => {
    const events = [
      makeEvent({
        event_type: "stage_entered",
        stage: "tdd",
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "stage_completed",
        stage: "tdd",
        timestamp: 1700000060,
      }),
    ];
    const testRuns = [
      makeEvent({
        event_type: "test_run",
        stage: "tdd",
        data: { passed: true, iteration: 1 },
      }),
      makeEvent({
        event_type: "test_run",
        stage: "tdd",
        data: { passed: false, iteration: 2 },
      }),
    ];
    renderWithContext(
      { stageName: "tdd", onBack: vi.fn() },
      { events, testRuns },
    );
    expect(screen.getByText("1 passed")).toBeInTheDocument();
    expect(screen.getByText("1 failed")).toBeInTheDocument();
    expect(screen.getByText("1m 0s")).toBeInTheDocument();
  });

  it("shows summary card with findings", () => {
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "critical", message: "XSS vulnerability" },
      }),
    ];
    renderWithContext(
      { stageName: "review", onBack: vi.fn() },
      { findings },
    );
    expect(screen.getByText("1 critical")).toBeInTheDocument();
  });
});
