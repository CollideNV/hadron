import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EventLog from "./EventLog";
import { makeEvent } from "../../test-utils";

describe("EventLog", () => {
  it("shows waiting message when no events", () => {
    render(<EventLog events={[]} />);
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument();
  });

  it("shows stage count", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "intake" }),
      makeEvent({ event_type: "stage_completed", stage: "intake" }),
    ];
    render(<EventLog events={events} currentStage="intake" />);
    expect(screen.getByText("1 stage")).toBeInTheDocument();
  });

  it("shows multiple stages", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "intake" }),
      makeEvent({ event_type: "stage_entered", stage: "implementation" }),
    ];
    render(<EventLog events={events} currentStage="implementation" />);
    expect(screen.getByText("2 stages")).toBeInTheDocument();
  });

  it("renders stage labels", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "implementation" }),
    ];
    render(<EventLog events={events} currentStage="implementation" status="running" />);
    expect(screen.getByText("Implementation")).toBeInTheDocument();
  });

  it("calls onSelectStage when view full log is clicked", async () => {
    const user = userEvent.setup();
    const onSelectStage = vi.fn();
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "intake" }),
    ];
    render(
      <EventLog
        events={events}
        currentStage="intake"
        status="running"
        onSelectStage={onSelectStage}
      />,
    );

    // Click the stage row to expand it
    const stageRow = screen.getByText("Intake");
    const clickTarget = stageRow.closest("[class*='cursor-pointer']");
    expect(clickTarget).not.toBeNull();
    await user.click(clickTarget!);

    // After expansion, click the "view full log" link
    const viewLink = screen.getByText(/view full log/i);
    await user.click(viewLink);
    expect(onSelectStage).toHaveBeenCalledWith("intake");
  });
});
