import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import CRListPage from "./CRListPage";
import { makeCRRun } from "../test-utils";

const mockListPipelines = vi.fn();

vi.mock("../api/client", () => ({
  listPipelines: (...args: unknown[]) => mockListPipelines(...args),
}));

beforeEach(() => {
  mockListPipelines.mockReset();
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
      expect(screen.getByText(/no pipeline runs yet/i)).toBeInTheDocument();
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
});
