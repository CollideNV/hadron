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
    stageDiffs: PipelineEvent[];
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
    stageDiffs: [],
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
    renderWithContext({ stageName: "implementation", onBack: vi.fn() });
    const implLabels = screen.getAllByText("implementation");
    expect(implLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/back/i)).toBeInTheDocument();
  });

  it("calls onBack when back button clicked", () => {
    const onBack = vi.fn();
    renderWithContext({ stageName: "implementation", onBack });
    fireEvent.click(screen.getByText(/back/i));
    expect(onBack).toHaveBeenCalled();
  });

  it("shows 'no agent sessions' when no activity", () => {
    renderWithContext({ stageName: "implementation", onBack: vi.fn() });
    expect(screen.getByText(/no agent sessions/i)).toBeInTheDocument();
  });

  it("shows agent session in sidebar and conversation", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "implementation",
        data: { role: "developer", repo: "backend" },
      }),
    ];
    const agentOutputs = [
      makeEvent({
        event_type: "agent_output",
        stage: "implementation",
        data: { role: "developer", repo: "backend", text: "Writing tests now" },
      }),
    ];
    renderWithContext(
      { stageName: "implementation", onBack: vi.fn() },
      { events, agentOutputs },
    );
    const devLabels = screen.getAllByText("developer");
    expect(devLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Writing tests now")).toBeInTheDocument();
  });

  it("shows summary card with test results", () => {
    const events = [
      makeEvent({
        event_type: "stage_entered",
        stage: "implementation",
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "stage_completed",
        stage: "implementation",
        timestamp: 1700000060,
      }),
    ];
    const testRuns = [
      makeEvent({
        event_type: "test_run",
        stage: "implementation",
        data: { passed: true, iteration: 1 },
      }),
      makeEvent({
        event_type: "test_run",
        stage: "implementation",
        data: { passed: false, iteration: 2 },
      }),
    ];
    renderWithContext(
      { stageName: "implementation", onBack: vi.fn() },
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

  it("shows review round tabs when multiple rounds exist", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", loop_iteration: 0 },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", input_tokens: 100, output_tokens: 50, cost_usd: 0.01, loop_iteration: 0 },
        timestamp: 1700000010,
      }),
      makeEvent({
        event_type: "agent_started",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", loop_iteration: 1 },
        timestamp: 1700000020,
      }),
      makeEvent({
        event_type: "agent_completed",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", input_tokens: 100, output_tokens: 50, cost_usd: 0.01, loop_iteration: 1 },
        timestamp: 1700000030,
      }),
    ];
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "major", message: "Round 1 issue", review_round: 0 },
      }),
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "info", message: "Round 2 note", review_round: 1 },
      }),
    ];
    renderWithContext(
      { stageName: "review", onBack: vi.fn() },
      { events, findings },
    );
    expect(screen.getByText("Review 1")).toBeInTheDocument();
    expect(screen.getByText("Review 2")).toBeInTheDocument();
  });

  it("defaults to latest round and filters findings accordingly", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", loop_iteration: 0 },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_started",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", loop_iteration: 1 },
        timestamp: 1700000020,
      }),
    ];
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "major", message: "Round 1 issue", review_round: 0 },
      }),
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "info", message: "Round 2 note", review_round: 1 },
      }),
    ];
    renderWithContext(
      { stageName: "review", onBack: vi.fn() },
      { events, findings },
    );

    // Defaults to latest round (Review 2) — shows only info finding
    expect(screen.getByText("1 info")).toBeInTheDocument();
    expect(screen.queryByText("1 major")).not.toBeInTheDocument();

    // Click "Review 1" to see round 1 findings
    fireEvent.click(screen.getByText("Review 1"));
    expect(screen.getByText("1 major")).toBeInTheDocument();
    expect(screen.queryByText("1 info")).not.toBeInTheDocument();
  });

  it("shows per-round findings in All view", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", loop_iteration: 0 },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_started",
        stage: "review:security_reviewer",
        data: { role: "security_reviewer", repo: "hadron", loop_iteration: 1 },
        timestamp: 1700000020,
      }),
    ];
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "major", message: "Round 1 issue", review_round: 0 },
      }),
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "info", message: "Round 2 note", review_round: 1 },
      }),
    ];
    renderWithContext(
      { stageName: "review", onBack: vi.fn() },
      { events, findings },
    );

    // Click "All" to see per-round breakdown
    fireEvent.click(screen.getByText("All"));
    // Both rounds' findings should be visible with round labels
    expect(screen.getByText("1 major")).toBeInTheDocument();
    expect(screen.getByText("1 info")).toBeInTheDocument();
  });

  it("does not show round tabs for non-review stages", () => {
    renderWithContext(
      { stageName: "implementation", onBack: vi.fn() },
    );
    expect(screen.queryByText("Review 1")).not.toBeInTheDocument();
  });

  it("shows Conversation and Changes tabs", () => {
    renderWithContext({ stageName: "implementation", onBack: vi.fn() });
    expect(screen.getByText("Conversation")).toBeInTheDocument();
    expect(screen.getByText("Changes")).toBeInTheDocument();
  });

  it("switches to Changes tab when clicked", () => {
    const stageDiffs = [
      makeEvent({
        event_type: "stage_diff",
        stage: "implementation",
        data: {
          repo: "backend",
          diff: "diff --git a/main.py b/main.py\n+hello",
          diff_truncated: false,
          stats: { files_changed: 1, insertions: 1, deletions: 0 },
        },
      }),
    ];
    renderWithContext(
      { stageName: "implementation", onBack: vi.fn() },
      { stageDiffs },
    );
    fireEvent.click(screen.getByText("Changes"));
    expect(screen.getByText("Code Diff")).toBeInTheDocument();
    expect(screen.getByText("1 file changed")).toBeInTheDocument();
  });

  it("shows (no changes captured) when no diffs", () => {
    renderWithContext({ stageName: "implementation", onBack: vi.fn() });
    fireEvent.click(screen.getByText("Changes"));
    expect(screen.getByText("(no changes captured)")).toBeInTheDocument();
  });

  it("does not show round tabs for single review round", () => {
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "minor", message: "Single round", review_round: 0 },
      }),
    ];
    renderWithContext(
      { stageName: "review", onBack: vi.fn() },
      { findings },
    );
    expect(screen.queryByText("Review 1")).not.toBeInTheDocument();
  });
});
