import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import CRListPage from "./CRListPage";
import { makeCRRun } from "../test-utils";

const mockListPipelines = vi.fn();
const mockTriggerPipeline = vi.fn();

vi.mock("../api/client", () => ({
  listPipelines: (...args: unknown[]) => mockListPipelines(...args),
  triggerPipeline: (...args: unknown[]) => mockTriggerPipeline(...args),
}));

beforeEach(() => {
  mockListPipelines.mockReset();
  mockTriggerPipeline.mockReset();
});

const sampleRuns = [
  makeCRRun({ cr_id: "cr-1", title: "Feature A", cost_usd: 0.5 }),
  makeCRRun({ cr_id: "cr-2", title: "Bug fix B", status: "completed" }),
];

describe("CRListPage", () => {
  it("shows loading state initially", () => {
    mockListPipelines.mockReturnValue(new Promise(() => {})); // never resolves
    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders pipeline runs after loading", async () => {
    mockListPipelines.mockResolvedValue(sampleRuns);

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Feature A")).toBeInTheDocument();
      expect(screen.getByText("Bug fix B")).toBeInTheDocument();
    });

    expect(screen.getByText("2 runs")).toBeInTheDocument();
  });

  it("shows empty state when no runs", async () => {
    mockListPipelines.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/no pipeline runs found/i)).toBeInTheDocument();
    });
  });

  it("shows error state on failure", async () => {
    mockListPipelines.mockRejectedValue(new Error("Connection refused"));

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Connection refused")).toBeInTheDocument();
    });
  });

  // New dialog integration tests

  it("renders a '+ New CR' button on the page", async () => {
    mockListPipelines.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /\+ new cr/i }),
      ).toBeInTheDocument();
    });
  });

  it("opens the creation dialog when '+ New CR' button is clicked", async () => {
    mockListPipelines.mockResolvedValue([]);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /\+ new cr/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /\+ new cr/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Create Change Request")).toBeInTheDocument();
  });

  it("closes the dialog when Cancel is clicked — list page remains visible", async () => {
    mockListPipelines.mockResolvedValue([]);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /\+ new cr/i }),
      ).toBeInTheDocument();
    });

    // Open dialog
    await user.click(screen.getByRole("button", { name: /\+ new cr/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // Cancel the dialog
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // List page is still visible
    expect(screen.getByText("Pipeline Runs")).toBeInTheDocument();
  });

  it("closes the dialog and refreshes the list after successful CR creation", async () => {
    mockListPipelines.mockResolvedValue(sampleRuns);
    mockTriggerPipeline.mockResolvedValue({
      cr_id: "cr-new-99",
      status: "pending",
    });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CRListPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /\+ new cr/i }),
      ).toBeInTheDocument();
    });

    // Open dialog
    await user.click(screen.getByRole("button", { name: /\+ new cr/i }));

    // Fill in the form
    await user.type(screen.getByPlaceholderText(/health check/i), "New Feature");
    await user.type(
      screen.getByPlaceholderText(/describe the change/i),
      "A detailed description",
    );

    // Submit
    await user.click(
      screen.getByRole("button", { name: /trigger pipeline/i }),
    );

    // Dialog closes
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    // triggerPipeline was called with the correct data
    expect(mockTriggerPipeline).toHaveBeenCalledWith(
      expect.objectContaining({ title: "New Feature" }),
    );

    // listPipelines was called again (refresh)
    expect(mockListPipelines).toHaveBeenCalledTimes(2);
  });
});
