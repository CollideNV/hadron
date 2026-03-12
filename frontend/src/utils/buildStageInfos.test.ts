import { describe, it, expect } from "vitest";
import { buildStageInfos, summarizeEvent, formatTs } from "./buildStageInfos";
import { makeEvent } from "../test-utils";

describe("buildStageInfos", () => {
  it("returns empty array for no events", () => {
    expect(buildStageInfos([])).toEqual([]);
  });

  it("creates stage info on stage_entered", () => {
    const events = [makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 })];
    const result = buildStageInfos(events);
    expect(result).toHaveLength(1);
    expect(result[0].stage).toBe("intake");
    expect(result[0].enteredAt).toBe(100);
    expect(result[0].completedAt).toBeNull();
  });

  it("marks stage completed on stage_completed", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 }),
      makeEvent({ event_type: "stage_completed", stage: "intake", timestamp: 200 }),
    ];
    const result = buildStageInfos(events);
    expect(result[0].completedAt).toBe(200);
  });

  it("tracks agent lifecycle", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "tdd", timestamp: 100 }),
      makeEvent({ event_type: "agent_started", stage: "tdd", timestamp: 110, data: { role: "developer", repo: "myrepo" } }),
      makeEvent({ event_type: "agent_tool_call", stage: "tdd", timestamp: 120, data: { role: "developer", repo: "myrepo", tool: "read_file" } }),
      makeEvent({ event_type: "agent_completed", stage: "tdd", timestamp: 130, data: { role: "developer", repo: "myrepo" } }),
    ];
    const result = buildStageInfos(events);
    expect(result[0].agents).toHaveLength(1);
    expect(result[0].agents[0].role).toBe("developer");
    expect(result[0].agents[0].repo).toBe("myrepo");
    expect(result[0].agents[0].startedAt).toBe(110);
    expect(result[0].agents[0].completedAt).toBe(130);
    expect(result[0].agents[0].toolCalls).toHaveLength(1);
  });

  it("handles sub-stages", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "review:security", timestamp: 100 }),
      makeEvent({ event_type: "agent_started", stage: "review:security", timestamp: 110, data: { role: "security_reviewer", repo: "" } }),
      makeEvent({ event_type: "agent_completed", stage: "review:security", timestamp: 120, data: { role: "security_reviewer", repo: "" } }),
      makeEvent({ event_type: "stage_completed", stage: "review:security", timestamp: 130 }),
    ];
    const result = buildStageInfos(events);
    const review = result.find((s) => s.stage === "review");
    expect(review).toBeDefined();
    expect(review!.subStages.size).toBe(1);
    const sub = review!.subStages.get("security")!;
    expect(sub.enteredAt).toBe(100);
    expect(sub.completedAt).toBe(130);
    expect(sub.agents).toHaveLength(1);
  });

  it("preserves pipeline stage order", () => {
    const events = [
      makeEvent({ event_type: "stage_entered", stage: "tdd", timestamp: 200 }),
      makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 }),
    ];
    const result = buildStageInfos(events);
    expect(result[0].stage).toBe("intake");
    expect(result[1].stage).toBe("tdd");
  });

  it("filters out stages with no activity", () => {
    const events = [makeEvent({ event_type: "stage_entered", stage: "intake", timestamp: 100 })];
    const result = buildStageInfos(events);
    expect(result).toHaveLength(1);
  });
});

describe("summarizeEvent", () => {
  it("summarizes test_run passed", () => {
    const event = makeEvent({ event_type: "test_run", data: { passed: true, iteration: 3 } });
    expect(summarizeEvent(event)).toBe("Tests PASSED (iteration 3)");
  });

  it("summarizes test_run failed", () => {
    const event = makeEvent({ event_type: "test_run", data: { passed: false, iteration: 1 } });
    expect(summarizeEvent(event)).toBe("Tests FAILED (iteration 1)");
  });

  it("summarizes review_finding", () => {
    const event = makeEvent({ event_type: "review_finding", data: { severity: "major", message: "SQL injection", file: "app.py" } });
    expect(summarizeEvent(event)).toBe("[major] SQL injection @ app.py");
  });

  it("summarizes cost_update", () => {
    const event = makeEvent({ event_type: "cost_update", data: { total_cost_usd: 1.5 } });
    expect(summarizeEvent(event)).toBe("$1.5000");
  });

  it("summarizes error", () => {
    const event = makeEvent({ event_type: "error", data: { message: "OOM" } });
    expect(summarizeEvent(event)).toBe("OOM");
  });

  it("returns event_type as default", () => {
    const event = makeEvent({ event_type: "custom_event", data: {} });
    expect(summarizeEvent(event)).toBe("custom_event");
  });
});

describe("formatTs", () => {
  it("formats a unix timestamp to HH:MM:SS", () => {
    const result = formatTs(1700000000);
    // Just verify it returns a string in expected format
    expect(result).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});
