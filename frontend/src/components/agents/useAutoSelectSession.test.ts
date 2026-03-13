import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAutoSelectSession } from "./useAutoSelectSession";
import type { AgentSession } from "./types";

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    role: "tdd_developer",
    repo: "",
    stage: "tdd",
    completed: false,
    items: [],
    inputTokens: 0,
    outputTokens: 0,
    costUsd: 0,
    roundCount: 0,
    throttleCount: 0,
    throttleSeconds: 0,
    modelBreakdown: {},
    loopIteration: 0,
    ...overrides,
  };
}

describe("useAutoSelectSession", () => {
  it("starts with index 0", () => {
    const sessions = [makeSession()];
    const { result } = renderHook(() => useAutoSelectSession(sessions));
    expect(result.current.selectedIndex).toBe(0);
    expect(result.current.selectedSession).toBe(sessions[0]);
  });

  it("auto-selects the latest active session", () => {
    const sessions = [
      makeSession({ role: "a", completed: true }),
      makeSession({ role: "b", completed: false }),
    ];
    const { result } = renderHook(() => useAutoSelectSession(sessions));
    expect(result.current.selectedIndex).toBe(1);
  });

  it("auto-selects latest active when multiple active sessions exist", () => {
    const sessions = [
      makeSession({ role: "a", completed: false }),
      makeSession({ role: "b", completed: false }),
      makeSession({ role: "c", completed: true }),
    ];
    const { result } = renderHook(() => useAutoSelectSession(sessions));
    expect(result.current.selectedIndex).toBe(1);
  });

  it("does not override when all sessions are completed", () => {
    const sessions = [
      makeSession({ role: "a", completed: true }),
      makeSession({ role: "b", completed: true }),
    ];
    const { result } = renderHook(() => useAutoSelectSession(sessions));
    expect(result.current.selectedIndex).toBe(0);
  });

  it("manual selection works via setSelectedIndex", () => {
    const sessions = [
      makeSession({ role: "a", completed: true }),
      makeSession({ role: "b", completed: false }),
    ];
    const { result } = renderHook(() => useAutoSelectSession(sessions));
    act(() => {
      result.current.setSelectedIndex(0);
    });
    expect(result.current.selectedIndex).toBe(0);
  });

  it("updates selection when sessions change and a new active appears", () => {
    const initial = [makeSession({ role: "a", completed: true })];
    const { result, rerender } = renderHook(
      ({ sessions }) => useAutoSelectSession(sessions),
      { initialProps: { sessions: initial } },
    );
    expect(result.current.selectedIndex).toBe(0);

    const updated = [
      makeSession({ role: "a", completed: true }),
      makeSession({ role: "b", completed: false }),
    ];
    rerender({ sessions: updated });
    expect(result.current.selectedIndex).toBe(1);
  });

  it("returns undefined selectedSession for empty sessions", () => {
    const { result } = renderHook(() => useAutoSelectSession([]));
    expect(result.current.selectedSession).toBeUndefined();
  });
});
