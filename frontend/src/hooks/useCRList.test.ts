import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useCRList } from "./useCRList";
import { makeCRRun } from "../test-utils";

const mockListPipelines = vi.fn();

vi.mock("../api/client", () => ({
  listPipelines: (...args: unknown[]) => mockListPipelines(...args),
}));

beforeEach(() => {
  mockListPipelines.mockReset();
});

const sampleRuns = [makeCRRun({ cr_id: "cr-1", title: "Test CR", created_at: "2026-01-01T00:00:00Z" })];

describe("useCRList", () => {
  it("fetches runs on mount", async () => {
    mockListPipelines.mockResolvedValue(sampleRuns);

    const { result } = renderHook(() => useCRList());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.runs).toEqual(sampleRuns);
    expect(result.current.error).toBeNull();
  });

  it("sets error on failure", async () => {
    mockListPipelines.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useCRList());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Network error");
    expect(result.current.runs).toEqual([]);
  });

  it("sets generic error for non-Error throws", async () => {
    mockListPipelines.mockRejectedValue("string error");

    const { result } = renderHook(() => useCRList());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Failed to load pipelines");
  });

  it("starts with loading true", () => {
    mockListPipelines.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCRList());
    expect(result.current.loading).toBe(true);
  });
});
