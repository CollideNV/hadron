import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import StageDetailView from "./StageDetailView";
import { makeEvent } from "../../test-utils";

vi.mock("../../api/client", () => ({
  sendNudge: vi.fn().mockResolvedValue({ status: "nudge_set" }),
}));

describe("StageDetailView", () => {
  const baseProps = {
    crId: "cr-1",
    stageName: "tdd",
    pipelineStatus: "running",
    onBack: vi.fn(),
  };

  it("shows stage name and back button", () => {
    render(
      <StageDetailView
        {...baseProps}
        events={[]}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    // "tdd" appears in both header and summary card
    const tddLabels = screen.getAllByText("tdd");
    expect(tddLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/back/i)).toBeInTheDocument();
  });

  it("calls onBack when back button clicked", () => {
    const onBack = vi.fn();
    render(
      <StageDetailView
        {...baseProps}
        onBack={onBack}
        events={[]}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    fireEvent.click(screen.getByText(/back/i));
    expect(onBack).toHaveBeenCalled();
  });

  it("shows 'no agent sessions' when no activity", () => {
    render(
      <StageDetailView
        {...baseProps}
        events={[]}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
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
    render(
      <StageDetailView
        {...baseProps}
        events={events}
        toolCalls={[]}
        agentOutputs={agentOutputs}
        agentNudges={[]}
        testRuns={[]}
        findings={[]}
      />,
    );
    // Session appears in sidebar
    const devLabels = screen.getAllByText("tdd developer");
    expect(devLabels.length).toBeGreaterThanOrEqual(1);
    // Output appears in conversation
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
    render(
      <StageDetailView
        {...baseProps}
        events={events}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        testRuns={testRuns}
        findings={[]}
      />,
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
    render(
      <StageDetailView
        {...baseProps}
        stageName="review"
        events={[]}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        testRuns={[]}
        findings={findings}
      />,
    );
    expect(screen.getByText("1 critical")).toBeInTheDocument();
  });
});
