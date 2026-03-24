import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LiveActivityFeed from "./LiveActivityFeed";

vi.mock("../../hooks/useGlobalActivity", () => ({
  useGlobalActivity: vi.fn(),
}));

import { useGlobalActivity } from "../../hooks/useGlobalActivity";
const mockUseGlobalActivity = vi.mocked(useGlobalActivity);

function renderFeed() {
  return render(
    <MemoryRouter>
      <LiveActivityFeed />
    </MemoryRouter>,
  );
}

describe("LiveActivityFeed", () => {
  it("shows empty state when no activities", () => {
    mockUseGlobalActivity.mockReturnValue({ activities: [], connected: true });

    renderFeed();

    expect(screen.getByText("No active pipelines right now.")).toBeInTheDocument();
    expect(screen.getByTestId("activity-feed")).toBeInTheDocument();
  });

  it("renders activities with CR info", () => {
    mockUseGlobalActivity.mockReturnValue({
      activities: [
        {
          cr_id: "cr-1",
          title: "Add login",
          stage: "implementation",
          status: "running",
          cost_usd: 0.5,
          last_event: "Tool: write_file",
          updated_at: Date.now(),
        },
      ],
      connected: true,
    });

    renderFeed();

    expect(screen.getByText("cr-1")).toBeInTheDocument();
    expect(screen.getByText("Add login")).toBeInTheDocument();
    expect(screen.getByText("Tool: write_file")).toBeInTheDocument();
    expect(screen.getByText("$0.5000")).toBeInTheDocument();
  });

  it("shows connection indicator as connected", () => {
    mockUseGlobalActivity.mockReturnValue({ activities: [], connected: true });

    renderFeed();

    const dot = screen.getByTestId("activity-connection");
    expect(dot).toHaveAttribute("title", "Connected");
  });

  it("shows connection indicator as disconnected", () => {
    mockUseGlobalActivity.mockReturnValue({ activities: [], connected: false });

    renderFeed();

    const dot = screen.getByTestId("activity-connection");
    expect(dot).toHaveAttribute("title", "Disconnected");
  });

  it("links to CR detail pages", () => {
    mockUseGlobalActivity.mockReturnValue({
      activities: [
        {
          cr_id: "cr-42",
          title: "Fix bug",
          stage: "review",
          status: "running",
          cost_usd: 0,
          updated_at: Date.now(),
        },
      ],
      connected: true,
    });

    renderFeed();

    const link = screen.getByTestId("activity-cr-42");
    expect(link).toHaveAttribute("href", "/cr/cr-42");
  });

  it("shows active count when activities exist", () => {
    mockUseGlobalActivity.mockReturnValue({
      activities: [
        { cr_id: "cr-1", title: "A", stage: "intake", status: "running", cost_usd: 0, updated_at: 1 },
        { cr_id: "cr-2", title: "B", stage: "review", status: "running", cost_usd: 0, updated_at: 2 },
      ],
      connected: true,
    });

    renderFeed();

    expect(screen.getByText("2 active")).toBeInTheDocument();
  });
});
