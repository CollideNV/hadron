import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useGlobalActivity } from "./useGlobalActivity";

// Capture the EventSource instance and its listeners
let esInstance: MockES;
type Listener = (e: { data: string }) => void;

class MockES {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  url: string;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    esInstance = this;
  }

  addEventListener(type: string, fn: Listener) {
    const list = this.listeners.get(type) || [];
    list.push(fn);
    this.listeners.set(type, list);
  }

  removeEventListener() {}

  close() {
    this.readyState = 2;
  }

  // Test helper: fire an event
  _fire(type: string, data: unknown) {
    const fns = this.listeners.get(type) || [];
    for (const fn of fns) fn({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).EventSource = MockES;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useGlobalActivity", () => {
  it("starts with empty activities and not connected", () => {
    const { result } = renderHook(() => useGlobalActivity());
    expect(result.current.activities).toEqual([]);
    expect(result.current.connected).toBe(false);
  });

  it("sets connected on open", () => {
    const { result } = renderHook(() => useGlobalActivity());

    act(() => {
      esInstance.onopen?.();
    });

    expect(result.current.connected).toBe(true);
  });

  it("sets disconnected on error", () => {
    const { result } = renderHook(() => useGlobalActivity());

    act(() => {
      esInstance.onopen?.();
    });
    expect(result.current.connected).toBe(true);

    act(() => {
      esInstance.onerror?.();
    });
    expect(result.current.connected).toBe(false);
  });

  it("handles cr_status events", () => {
    const { result } = renderHook(() => useGlobalActivity());

    act(() => {
      esInstance._fire("cr_status", {
        cr_id: "cr-1",
        title: "Feature A",
        stage: "implementation",
        status: "running",
      });
    });

    expect(result.current.activities).toHaveLength(1);
    expect(result.current.activities[0].cr_id).toBe("cr-1");
    expect(result.current.activities[0].title).toBe("Feature A");
    expect(result.current.activities[0].stage).toBe("implementation");
  });

  it("handles stage_entered events", () => {
    const { result } = renderHook(() => useGlobalActivity());

    // First add a CR
    act(() => {
      esInstance._fire("cr_status", {
        cr_id: "cr-1",
        title: "Feature A",
        stage: "intake",
        status: "running",
      });
    });

    // Then update stage
    act(() => {
      esInstance._fire("stage_entered", {
        cr_id: "cr-1",
        event_type: "stage_entered",
        stage: "review",
        data: {},
        timestamp: 1700000000,
      });
    });

    expect(result.current.activities[0].stage).toBe("review");
    expect(result.current.activities[0].last_event).toBe("Entered review");
  });

  it("handles cost_update events", () => {
    const { result } = renderHook(() => useGlobalActivity());

    act(() => {
      esInstance._fire("cr_status", {
        cr_id: "cr-1",
        title: "Feature A",
        stage: "intake",
        status: "running",
      });
    });

    act(() => {
      esInstance._fire("cost_update", {
        cr_id: "cr-1",
        event_type: "cost_update",
        stage: "implementation",
        data: { total_cost_usd: 1.23 },
        timestamp: 1700000000,
      });
    });

    expect(result.current.activities[0].cost_usd).toBe(1.23);
  });

  it("handles pipeline_completed events", () => {
    const { result } = renderHook(() => useGlobalActivity());

    act(() => {
      esInstance._fire("cr_status", {
        cr_id: "cr-1",
        title: "Feature A",
        stage: "delivery",
        status: "running",
      });
    });

    act(() => {
      esInstance._fire("pipeline_completed", {
        cr_id: "cr-1",
        event_type: "pipeline_completed",
        stage: "delivery",
        data: {},
        timestamp: 1700000000,
      });
    });

    expect(result.current.activities[0].status).toBe("completed");
  });

  it("sorts activities by updated_at descending", () => {
    // Use fake timers to control Date.now()
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));

    const { result } = renderHook(() => useGlobalActivity());

    act(() => {
      esInstance._fire("cr_status", {
        cr_id: "cr-1",
        title: "Older",
        stage: "intake",
        status: "running",
      });
    });

    // Advance time so cr-2 gets a newer timestamp
    vi.advanceTimersByTime(1000);

    act(() => {
      esInstance._fire("cr_status", {
        cr_id: "cr-2",
        title: "Newer",
        stage: "review",
        status: "running",
      });
    });

    // cr-2 should be first (more recent)
    expect(result.current.activities[0].cr_id).toBe("cr-2");
    expect(result.current.activities[1].cr_id).toBe("cr-1");

    vi.useRealTimers();
  });

  it("closes EventSource on unmount", () => {
    const { unmount } = renderHook(() => useGlobalActivity());
    const closeSpy = vi.spyOn(esInstance, "close");

    unmount();

    expect(closeSpy).toHaveBeenCalled();
  });
});
