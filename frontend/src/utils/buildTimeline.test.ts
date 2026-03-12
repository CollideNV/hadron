import { describe, it, expect } from "vitest";
import { buildTimeline } from "./buildTimeline";
import type { ConversationItem } from "../components/agents/types";
import { makeEvent } from "../test-utils";

describe("buildTimeline", () => {
  it("returns empty array for empty input", () => {
    expect(buildTimeline([], [], [])).toEqual([]);
  });

  it("pairs tool_call + tool_result", () => {
    const items: ConversationItem[] = [
      { type: "tool_call", tool: "read_file", input: { path: "a.ts" }, round: 1, ts: 100 },
      { type: "tool_result", tool: "read_file", result: "contents", round: 1, ts: 101 },
    ];
    const result = buildTimeline(items, [], []);
    expect(result).toHaveLength(1);
    expect(result[0].kind).toBe("tool");
    if (result[0].kind === "tool") {
      expect(result[0].call.tool).toBe("read_file");
      expect(result[0].result).toBeDefined();
      expect(result[0].result!.result).toBe("contents");
    }
  });

  it("handles orphan tool_result", () => {
    const items: ConversationItem[] = [
      { type: "tool_result", tool: "write_file", result: "ok", round: 1, ts: 100 },
    ];
    const result = buildTimeline(items, [], []);
    expect(result).toHaveLength(1);
    expect(result[0].kind).toBe("tool");
    if (result[0].kind === "tool") {
      expect(result[0].result!.result).toBe("ok");
    }
  });

  it("includes nudges", () => {
    const items: ConversationItem[] = [
      { type: "nudge", text: "focus on tests", ts: 100 },
    ];
    const result = buildTimeline(items, [], []);
    expect(result).toHaveLength(1);
    expect(result[0].kind).toBe("nudge");
  });

  it("interleaves test runs by timestamp", () => {
    const items: ConversationItem[] = [
      { type: "output", text: "hello", round: 1, ts: 100 },
    ];
    const testRuns = [makeEvent({ event_type: "test_run", timestamp: 50 })];
    const result = buildTimeline(items, testRuns, []);
    expect(result).toHaveLength(2);
    expect(result[0].kind).toBe("test_run");
    expect(result[1].kind).toBe("output");
  });

  it("interleaves findings by timestamp", () => {
    const items: ConversationItem[] = [
      { type: "output", text: "done", round: 1, ts: 200 },
    ];
    const findings = [makeEvent({ event_type: "review_finding", timestamp: 150 })];
    const result = buildTimeline(items, [], findings);
    expect(result).toHaveLength(2);
    expect(result[0].kind).toBe("finding");
    expect(result[1].kind).toBe("output");
  });

  it("sorts all entries by timestamp", () => {
    const items: ConversationItem[] = [
      { type: "output", text: "b", round: 1, ts: 200 },
      { type: "output", text: "a", round: 1, ts: 100 },
    ];
    const result = buildTimeline(items, [], []);
    expect(result[0].ts).toBe(100);
    expect(result[1].ts).toBe(200);
  });

  it("handles unmatched tool_call (no result)", () => {
    const items: ConversationItem[] = [
      { type: "tool_call", tool: "read_file", input: {}, round: 1, ts: 100 },
      { type: "output", text: "done", round: 1, ts: 200 },
    ];
    const result = buildTimeline(items, [], []);
    expect(result).toHaveLength(2);
    expect(result[0].kind).toBe("tool");
    if (result[0].kind === "tool") {
      expect(result[0].result).toBeUndefined();
    }
  });
});
