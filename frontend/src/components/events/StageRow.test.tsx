import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StageRow from "./StageRow";
import type { StageInfo, AgentSpan } from "../../utils/buildStageInfos";
import { makeEvent } from "../../test-utils";

function makeStageInfo(overrides: Partial<StageInfo> = {}): StageInfo {
  return {
    stage: "implementation",
    enteredAt: 1700000000,
    completedAt: 1700000120,
    events: [],
    agents: [],
    subStages: new Map(),
    ...overrides,
  };
}

function makeAgent(overrides: Partial<AgentSpan> = {}): AgentSpan {
  return {
    role: "developer",
    repo: "my-repo",
    startedAt: 1700000000,
    completedAt: 1700000060,
    toolCalls: [],
    ...overrides,
  };
}

describe("StageRow", () => {
  const defaultProps = {
    currentStage: "review",
    status: "running",
    onSelect: vi.fn(),
  };

  it("renders stage label", () => {
    render(<StageRow info={makeStageInfo()} {...defaultProps} />);
    expect(screen.getByText("Implementation")).toBeInTheDocument();
  });

  it("shows duration for completed stage", () => {
    render(<StageRow info={makeStageInfo()} {...defaultProps} />);
    expect(screen.getByText("2m 0s")).toBeInTheDocument();
  });

  it("shows '...' for current in-progress stage", () => {
    render(
      <StageRow
        info={makeStageInfo({ completedAt: null })}
        currentStage="implementation"
        status="running"
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("...")).toBeInTheDocument();
  });

  it("shows empty duration for non-current incomplete stage", () => {
    render(
      <StageRow
        info={makeStageInfo({ completedAt: null })}
        {...defaultProps}
      />,
    );
    // Duration cell should be empty (no "..." since not current)
    expect(screen.queryByText("...")).not.toBeInTheDocument();
  });

  it("shows agent count badge", () => {
    const agents = [makeAgent(), makeAgent({ role: "reviewer" })];
    render(<StageRow info={makeStageInfo({ agents })} {...defaultProps} />);
    expect(screen.getByText("2 agents")).toBeInTheDocument();
  });

  it("shows singular 'agent' for one agent", () => {
    render(<StageRow info={makeStageInfo({ agents: [makeAgent()] })} {...defaultProps} />);
    expect(screen.getByText("1 agent")).toBeInTheDocument();
  });

  it("shows PASS badge for passing test_run events", () => {
    const events = [
      makeEvent({ event_type: "test_run", stage: "implementation", data: { passed: true, iteration: 1 } }),
    ];
    render(<StageRow info={makeStageInfo({ events })} {...defaultProps} />);
    expect(screen.getByText("PASS")).toBeInTheDocument();
  });

  it("shows FAIL badge for failing test_run events", () => {
    const events = [
      makeEvent({ event_type: "test_run", stage: "implementation", data: { passed: false, iteration: 1 } }),
    ];
    render(<StageRow info={makeStageInfo({ events })} {...defaultProps} />);
    expect(screen.getByText("FAIL")).toBeInTheDocument();
  });

  it("shows findings count badge", () => {
    const events = [
      makeEvent({ event_type: "review_finding", stage: "review", data: { severity: "high", message: "Issue" } }),
      makeEvent({ event_type: "review_finding", stage: "review", data: { severity: "low", message: "Minor" } }),
    ];
    render(<StageRow info={makeStageInfo({ events })} {...defaultProps} />);
    expect(screen.getByText("2 findings")).toBeInTheDocument();
  });

  it("shows singular 'finding' for one finding", () => {
    const events = [
      makeEvent({ event_type: "review_finding", stage: "review", data: { severity: "high", message: "Issue" } }),
    ];
    render(<StageRow info={makeStageInfo({ events })} {...defaultProps} />);
    expect(screen.getByText("1 finding")).toBeInTheDocument();
  });

  it("has aria-expanded attribute", () => {
    render(<StageRow info={makeStageInfo()} {...defaultProps} />);
    const button = screen.getByRole("button", { name: /Implementation/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("expands on click to show agents", async () => {
    const user = userEvent.setup();
    const agents = [makeAgent()];
    render(<StageRow info={makeStageInfo({ agents })} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /Implementation/i }));
    expect(screen.getByText("developer")).toBeInTheDocument();
  });

  it("shows 'View full log' button when expanded", async () => {
    const user = userEvent.setup();
    render(<StageRow info={makeStageInfo()} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /Implementation/i }));
    expect(screen.getByText(/View full log/)).toBeInTheDocument();
  });

  it("calls onSelect when 'View full log' is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<StageRow info={makeStageInfo()} currentStage="review" status="running" onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: /Implementation/i }));
    await user.click(screen.getByText(/View full log/));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("renders sub-stages when expanded", async () => {
    const user = userEvent.setup();
    const subStages = new Map([
      ["red", { label: "red", enteredAt: 1700000000, completedAt: 1700000030, agents: [makeAgent({ role: "impl_dev" })] }],
      ["green", { label: "green", enteredAt: 1700000030, completedAt: null, agents: [] }],
    ]);
    render(<StageRow info={makeStageInfo({ subStages })} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /Implementation/i }));
    expect(screen.getByText("red")).toBeInTheDocument();
    expect(screen.getByText("green")).toBeInTheDocument();
    expect(screen.getByText("impl_dev")).toBeInTheDocument();
  });

  it("shows non-agent events in expanded view", async () => {
    const user = userEvent.setup();
    const events = [
      makeEvent({ event_type: "test_run", stage: "implementation", data: { passed: true, iteration: 1 } }),
    ];
    render(<StageRow info={makeStageInfo({ events })} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /Implementation/i }));
    expect(screen.getByText(/Tests PASSED/)).toBeInTheDocument();
  });

  it("shows failed status styling for current failed stage", () => {
    render(
      <StageRow
        info={makeStageInfo({ completedAt: null })}
        currentStage="implementation"
        status="failed"
        onSelect={vi.fn()}
      />,
    );
    // The FailIcon SVG should be present
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("shows paused status styling for current paused stage", () => {
    render(
      <StageRow
        info={makeStageInfo({ completedAt: null })}
        currentStage="implementation"
        status="paused"
        onSelect={vi.fn()}
      />,
    );
    // PauseIcon uses rect elements
    const rects = document.querySelectorAll("rect");
    expect(rects.length).toBeGreaterThan(0);
  });

  it("filters out agent/stage events from the expanded event list", async () => {
    const user = userEvent.setup();
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "implementation" }),
      makeEvent({ event_type: "agent_started", stage: "implementation", data: { role: "dev", repo: "" } }),
      makeEvent({ event_type: "cost_update", stage: "implementation", data: { total_cost_usd: 0.5 } }),
    ];
    render(<StageRow info={makeStageInfo({ events })} {...defaultProps} />);
    await user.click(screen.getByRole("button", { name: /Implementation/i }));
    // Only cost_update should be shown as a summarized event
    expect(screen.getByText("$0.5000")).toBeInTheDocument();
    // stage_entered and agent_started should be filtered out
    expect(screen.queryByText("stage entered")).not.toBeInTheDocument();
    expect(screen.queryByText("agent started")).not.toBeInTheDocument();
  });
});
