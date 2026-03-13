import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StageDetailLog from "./StageDetailLog";
import { makeEvent } from "../../test-utils";

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView
  Element.prototype.scrollIntoView = vi.fn();
});

describe("StageDetailLog", () => {
  it("shows stage name in header", () => {
    render(
      <StageDetailLog events={[]} stageName="tdd" onBack={vi.fn()} />,
    );
    expect(screen.getByText("tdd Log")).toBeInTheDocument();
  });

  it("shows event count", () => {
    const events = [
      makeEvent({ event_type: "stage_entered" }),
      makeEvent({ event_type: "agent_started", data: { role: "tdd_dev", repo: "" } }),
    ];
    render(
      <StageDetailLog events={events} stageName="tdd" onBack={vi.fn()} />,
    );
    expect(screen.getByText("2 events")).toBeInTheDocument();
  });

  it("shows 1 event (singular)", () => {
    const events = [makeEvent({ event_type: "stage_entered" })];
    render(
      <StageDetailLog events={events} stageName="tdd" onBack={vi.fn()} />,
    );
    expect(screen.getByText("1 event")).toBeInTheDocument();
  });

  it("renders back button that calls onBack", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    render(
      <StageDetailLog events={[]} stageName="tdd" onBack={onBack} />,
    );

    const backButton = screen.getByText(/all stages/i);
    await user.click(backButton);
    expect(onBack).toHaveBeenCalled();
  });

  it("summarizes pipeline events", () => {
    const events = [
      makeEvent({ event_type: "pipeline_started" }),
      makeEvent({
        event_type: "test_run",
        data: { passed: true, iteration: 1 },
      }),
    ];
    render(
      <StageDetailLog events={events} stageName="tdd" onBack={vi.fn()} />,
    );
    expect(screen.getByText("Pipeline started")).toBeInTheDocument();
    expect(screen.getByText(/Tests PASSED/)).toBeInTheDocument();
  });

  it("shows sub-stage headers", () => {
    const events = [
      makeEvent({
        event_type: "stage_entered",
        stage: "review:security_review",
      }),
    ];
    render(
      <StageDetailLog events={events} stageName="review" onBack={vi.fn()} />,
    );
    expect(screen.getByText("security review")).toBeInTheDocument();
  });
});
