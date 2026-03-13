import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TestResultsPanel from "./TestResultsPanel";
import type { PipelineEvent } from "../../api/types";

function makeTestRun(
  passed: boolean,
  iteration: number,
  output = "",
): PipelineEvent {
  return {
    cr_id: "cr-1",
    event_type: "test_run",
    stage: "implementation",
    data: { passed, iteration, output_tail: output },
    timestamp: 1700000000,
  };
}

describe("TestResultsPanel", () => {
  it("shows empty state when no test runs", () => {
    render(<TestResultsPanel testRuns={[]} />);
    expect(screen.getByText(/no test runs yet/i)).toBeInTheDocument();
  });

  it("shows PASS for passing test", () => {
    render(<TestResultsPanel testRuns={[makeTestRun(true, 1)]} />);
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/iteration 1/i)).toBeInTheDocument();
  });

  it("shows FAIL for failing test", () => {
    render(<TestResultsPanel testRuns={[makeTestRun(false, 2)]} />);
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(screen.getByText(/iteration 2/i)).toBeInTheDocument();
  });

  it("shows multiple test runs", () => {
    render(
      <TestResultsPanel
        testRuns={[makeTestRun(false, 1), makeTestRun(true, 2)]}
      />,
    );
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
  });

  it("expands to show test output", async () => {
    const user = userEvent.setup();
    render(
      <TestResultsPanel
        testRuns={[makeTestRun(false, 1, "FAILED test_foo.py::test_bar")]}
      />,
    );

    await user.click(screen.getByText(/show output/i));
    expect(screen.getByText(/FAILED test_foo/)).toBeInTheDocument();
  });

  it("hides show button when no output", () => {
    render(<TestResultsPanel testRuns={[makeTestRun(true, 1, "")]} />);
    expect(screen.queryByText(/show output/i)).not.toBeInTheDocument();
  });
});
