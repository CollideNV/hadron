import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StageTimeline from "./StageTimeline";

describe("StageTimeline", () => {
  it("renders all stage groups", () => {
    render(
      <StageTimeline
        currentStage=""
        completedStages={new Set()}
        status="connecting"
      />,
    );
    expect(screen.getByText("Understand")).toBeInTheDocument();
    expect(screen.getByText("Specify")).toBeInTheDocument();
    expect(screen.getByText("Build")).toBeInTheDocument();
    expect(screen.getByText("Validate")).toBeInTheDocument();
    expect(screen.getByText("Ship")).toBeInTheDocument();
  });

  it("renders all 12 stage labels", () => {
    render(
      <StageTimeline
        currentStage=""
        completedStages={new Set()}
        status="connecting"
      />,
    );
    expect(screen.getByText("Intake")).toBeInTheDocument();
    expect(screen.getByText("Repo ID")).toBeInTheDocument();
    expect(screen.getByText("Worktree")).toBeInTheDocument();
    expect(screen.getByText("Translate")).toBeInTheDocument();
    expect(screen.getByText("Verify")).toBeInTheDocument();
    expect(screen.getByText("TDD")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("Rebase")).toBeInTheDocument();
    expect(screen.getByText("Deliver")).toBeInTheDocument();
    expect(screen.getByText("Gate")).toBeInTheDocument();
    expect(screen.getByText("Release")).toBeInTheDocument();
    expect(screen.getByText("Retro")).toBeInTheDocument();
  });

  it("shows checkmark for completed stages", () => {
    const { container } = render(
      <StageTimeline
        currentStage="tdd"
        completedStages={new Set(["intake", "repo_id", "worktree_setup"])}
        status="running"
      />,
    );
    // Completed stages should render checkmark SVGs (path with d="M3 7l3 3 5-5")
    const checkmarks = container.querySelectorAll(
      'path[d="M3 7l3 3 5-5"]',
    );
    expect(checkmarks.length).toBe(3);
  });

  it("shows icon text for current non-completed stage", () => {
    render(
      <StageTimeline
        currentStage="tdd"
        completedStages={new Set()}
        status="running"
      />,
    );
    // TDD stage should show "TD" icon text (not a checkmark)
    expect(screen.getByText("TD")).toBeInTheDocument();
  });

  it("calls onSelectStage when a stage is clicked", async () => {
    const onSelectStage = vi.fn();
    const user = userEvent.setup();
    render(
      <StageTimeline
        currentStage="tdd"
        completedStages={new Set(["intake"])}
        status="running"
        onSelectStage={onSelectStage}
      />,
    );

    await user.click(screen.getByText("Intake"));
    expect(onSelectStage).toHaveBeenCalledWith("intake");
  });

  it("shows X icon for failed current stage", () => {
    const { container } = render(
      <StageTimeline
        currentStage="tdd"
        completedStages={new Set()}
        status="failed"
      />,
    );
    // Failed stage renders X SVG with path containing "M3 3l6 6M9 3l-6 6"
    const xPaths = container.querySelectorAll(
      'path[d="M3 3l6 6M9 3l-6 6"]',
    );
    expect(xPaths.length).toBe(1);
  });
});
