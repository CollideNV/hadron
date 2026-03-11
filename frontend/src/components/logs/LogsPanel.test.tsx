import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LogsPanel from "./LogsPanel";

const mockGetWorkerLogs = vi.fn();

vi.mock("../../api/client", () => ({
  getWorkerLogs: (...args: unknown[]) => mockGetWorkerLogs(...args),
}));

beforeEach(() => {
  mockGetWorkerLogs.mockReset();
});

describe("LogsPanel", () => {
  it("fetches and displays logs on mount", async () => {
    mockGetWorkerLogs.mockResolvedValue("INFO: Starting pipeline\nINFO: Done");

    render(<LogsPanel crId="cr-1" pipelineStatus="completed" />);

    await waitFor(() => {
      expect(screen.getByText(/starting pipeline/i)).toBeInTheDocument();
    });
  });

  it("shows no logs message when empty", async () => {
    mockGetWorkerLogs.mockResolvedValue("");

    render(<LogsPanel crId="cr-1" pipelineStatus="completed" />);

    await waitFor(() => {
      expect(screen.getByText(/no logs available/i)).toBeInTheDocument();
    });
  });

  it("filters logs by text", async () => {
    mockGetWorkerLogs.mockResolvedValue(
      "INFO: hello\nERROR: something broke\nINFO: world",
    );
    const user = userEvent.setup();

    render(<LogsPanel crId="cr-1" pipelineStatus="completed" />);

    await waitFor(() => {
      expect(screen.getByText(/hello/)).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/filter/i), "ERROR");

    // Only the ERROR line should be visible
    await waitFor(() => {
      expect(screen.getByText(/something broke/)).toBeInTheDocument();
      expect(screen.queryByText(/hello/)).not.toBeInTheDocument();
    });
  });

  it("renders refresh button", async () => {
    mockGetWorkerLogs.mockResolvedValue("logs");

    render(<LogsPanel crId="cr-1" pipelineStatus="completed" />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /refresh/i }),
      ).toBeInTheDocument();
    });
  });

  it("has auto-refresh checkbox", () => {
    mockGetWorkerLogs.mockResolvedValue("");
    render(<LogsPanel crId="cr-1" pipelineStatus="running" />);

    expect(screen.getByText(/auto-refresh/i)).toBeInTheDocument();
  });
});
