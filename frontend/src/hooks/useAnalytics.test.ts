import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAnalyticsSummary, useAnalyticsCost } from "./useAnalytics";

const mockGetAnalyticsSummary = vi.fn();
const mockGetAnalyticsCost = vi.fn();

vi.mock("../api/client", () => ({
  getAnalyticsSummary: (...args: unknown[]) => mockGetAnalyticsSummary(...args),
  getAnalyticsCost: (...args: unknown[]) => mockGetAnalyticsCost(...args),
}));

beforeEach(() => {
  mockGetAnalyticsSummary.mockReset();
  mockGetAnalyticsCost.mockReset();
});

const fakeSummary = {
  total_runs: 10,
  status_counts: { completed: 7, failed: 3 },
  success_rate: 0.7,
  total_cost_usd: 5.0,
  avg_cost_usd: 0.5,
  stage_durations: [],
  daily_stats: [],
};

const fakeCost = {
  group_by: "repo",
  total_cost_usd: 2.0,
  groups: [{ key: "acme", label: "acme", cost_usd: 2.0, runs: 5, tokens: 0 }],
};

describe("useAnalyticsSummary", () => {
  it("fetches summary on mount", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(fakeSummary);

    const { result } = renderHook(() => useAnalyticsSummary(30, 60_000));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(fakeSummary);
    expect(result.current.error).toBeNull();
    expect(mockGetAnalyticsSummary).toHaveBeenCalledWith(30);
  });

  it("sets error on failure", async () => {
    mockGetAnalyticsSummary.mockRejectedValue(new Error("Server error"));

    const { result } = renderHook(() => useAnalyticsSummary(30, 60_000));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Server error");
    expect(result.current.data).toBeNull();
  });

  it("starts with loading true", () => {
    mockGetAnalyticsSummary.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsSummary(30, 60_000));
    expect(result.current.loading).toBe(true);
  });
});

describe("useAnalyticsCost", () => {
  it("fetches cost with groupBy arg", async () => {
    mockGetAnalyticsCost.mockResolvedValue(fakeCost);

    const { result } = renderHook(() => useAnalyticsCost("repo", 60_000));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(fakeCost);
    expect(mockGetAnalyticsCost).toHaveBeenCalledWith("repo");
  });

  it("sets error on failure", async () => {
    mockGetAnalyticsCost.mockRejectedValue(new Error("Cost fetch failed"));

    const { result } = renderHook(() => useAnalyticsCost("stage", 60_000));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Cost fetch failed");
  });
});
