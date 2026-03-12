import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useCRDetail } from "./useCRDetail";
import type { CRRunDetail, PipelineEvent } from "../api/types";
import { makeEvent } from "../test-utils";

// Mock useEventStream
const mockStream = {
  status: "running" as string,
  events: [] as PipelineEvent[],
  toolCalls: [] as PipelineEvent[],
  agentOutputs: [] as PipelineEvent[],
  agentNudges: [] as PipelineEvent[],
  testRuns: [] as PipelineEvent[],
  reviewFindings: [] as PipelineEvent[],
  costUsd: 0,
  currentStage: "intake",
};

vi.mock("./useEventStream", () => ({
  useEventStream: vi.fn(() => mockStream),
}));

const mockGetPipelineStatus = vi.fn();
vi.mock("../api/client", () => ({
  getPipelineStatus: (...args: unknown[]) => mockGetPipelineStatus(...args),
}));

function makeCRRunDetail(overrides: Partial<CRRunDetail> = {}): CRRunDetail {
  return {
    cr_id: "cr-1",
    title: "Test CR",
    status: "running",
    source: "api",
    external_id: null,
    cost_usd: 0.5,
    error: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    repos: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockStream.status = "running";
  mockStream.events = [];
  mockStream.toolCalls = [];
  mockStream.agentOutputs = [];
  mockStream.agentNudges = [];
  mockStream.testRuns = [];
  mockStream.reviewFindings = [];
  mockGetPipelineStatus.mockResolvedValue(makeCRRunDetail());
});

describe("useCRDetail", () => {
  it("fetches CR on mount when crId is provided", async () => {
    renderHook(() => useCRDetail("cr-1"));
    expect(mockGetPipelineStatus).toHaveBeenCalledWith("cr-1");
  });

  it("does not fetch when crId is undefined", () => {
    renderHook(() => useCRDetail(undefined));
    expect(mockGetPipelineStatus).not.toHaveBeenCalled();
  });

  it("returns title from fetched CR", async () => {
    mockGetPipelineStatus.mockResolvedValue(makeCRRunDetail({ title: "My Feature" }));
    const { result } = renderHook(() => useCRDetail("cr-1"));
    await waitFor(() => expect(result.current.title).toBe("My Feature"));
  });

  it("returns 'Loading...' before CR is fetched", () => {
    mockGetPipelineStatus.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useCRDetail("cr-1"));
    expect(result.current.title).toBe("Loading...");
  });

  it("returns stream status as displayStatus when stream is active", () => {
    mockStream.status = "running";
    const { result } = renderHook(() => useCRDetail("cr-1"));
    expect(result.current.displayStatus).toBe("running");
  });

  it("trusts API status when stream says running but API says paused", async () => {
    mockStream.status = "running";
    mockGetPipelineStatus.mockResolvedValue(makeCRRunDetail({ status: "paused" }));
    const { result } = renderHook(() => useCRDetail("cr-1"));
    await waitFor(() => expect(result.current.displayStatus).toBe("paused"));
  });

  it("trusts API status when stream says running but API says failed", async () => {
    mockStream.status = "running";
    mockGetPipelineStatus.mockResolvedValue(makeCRRunDetail({ status: "failed" }));
    const { result } = renderHook(() => useCRDetail("cr-1"));
    await waitFor(() => expect(result.current.displayStatus).toBe("failed"));
  });

  it("trusts API status when stream says running but API says completed", async () => {
    mockStream.status = "running";
    mockGetPipelineStatus.mockResolvedValue(makeCRRunDetail({ status: "completed" }));
    const { result } = renderHook(() => useCRDetail("cr-1"));
    await waitFor(() => expect(result.current.displayStatus).toBe("completed"));
  });

  it("uses apiStatus when stream is connecting", async () => {
    mockStream.status = "connecting";
    mockGetPipelineStatus.mockResolvedValue(makeCRRunDetail({ status: "paused" }));
    const { result } = renderHook(() => useCRDetail("cr-1"));
    await waitFor(() => expect(result.current.displayStatus).toBe("paused"));
  });

  it("returns 'pending' when connecting and no API response yet", () => {
    mockStream.status = "connecting";
    mockGetPipelineStatus.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCRDetail("cr-1"));
    expect(result.current.displayStatus).toBe("pending");
  });

  describe("filterByStage", () => {
    it("returns all events when stage is null", () => {
      const ev1 = makeEvent({ event_type: "agent_started", stage: "tdd" });
      const ev2 = makeEvent({ event_type: "agent_started", stage: "review" });
      mockStream.events = [ev1, ev2];
      mockStream.toolCalls = [makeEvent({ event_type: "agent_tool_call", stage: "tdd" })];

      const { result } = renderHook(() => useCRDetail("cr-1"));
      const filtered = result.current.filterByStage(null);
      expect(filtered.events).toHaveLength(2);
      expect(filtered.toolCalls).toHaveLength(1);
    });

    it("filters events by stage with pipeline-level events included", () => {
      const events = [
        makeEvent({ event_type: "pipeline_started", stage: "" }),
        makeEvent({ event_type: "agent_started", stage: "tdd" }),
        makeEvent({ event_type: "agent_started", stage: "review" }),
      ];
      mockStream.events = events;

      const { result } = renderHook(() => useCRDetail("cr-1"));
      const filtered = result.current.filterByStage("tdd");
      expect(filtered.events).toHaveLength(2); // pipeline_started + tdd event
    });

    it("includes sub-stage events with prefix matching for toolCalls", () => {
      const toolCalls = [
        makeEvent({ event_type: "agent_tool_call", stage: "tdd" }),
        makeEvent({ event_type: "agent_tool_call", stage: "tdd:red" }),
        makeEvent({ event_type: "agent_tool_call", stage: "review" }),
      ];
      mockStream.toolCalls = toolCalls;

      const { result } = renderHook(() => useCRDetail("cr-1"));
      const filtered = result.current.filterByStage("tdd");
      expect(filtered.toolCalls).toHaveLength(2); // tdd + tdd:red
    });

    it("uses exact match for testRuns and findings", () => {
      mockStream.testRuns = [
        makeEvent({ event_type: "test_run", stage: "tdd", data: { passed: true } }),
        makeEvent({ event_type: "test_run", stage: "tdd:red", data: { passed: false } }),
      ];
      mockStream.reviewFindings = [
        makeEvent({ event_type: "review_finding", stage: "review" }),
        makeEvent({ event_type: "review_finding", stage: "review:security" }),
      ];

      const { result } = renderHook(() => useCRDetail("cr-1"));

      const tddFiltered = result.current.filterByStage("tdd");
      expect(tddFiltered.testRuns).toHaveLength(1); // exact match only

      const reviewFiltered = result.current.filterByStage("review");
      expect(reviewFiltered.findings).toHaveLength(1); // exact match only
    });
  });
});
