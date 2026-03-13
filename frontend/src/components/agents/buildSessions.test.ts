import { describe, it, expect } from "vitest";
import { buildSessions } from "./buildSessions";
import { makeEvent } from "../../test-utils";

describe("buildSessions", () => {
  it("returns empty array for no events", () => {
    expect(buildSessions([], [], [], [])).toEqual([]);
  });

  it("creates session from agent_started event", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "backend", model: "claude-3-5-sonnet-20241022" },
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].role).toBe("tdd_developer");
    expect(sessions[0].repo).toBe("backend");
    expect(sessions[0].stage).toBe("tdd");
    expect(sessions[0].model).toBe("claude-3-5-sonnet-20241022");
    expect(sessions[0].completed).toBe(false);
  });

  it("marks session completed from agent_completed event", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "", input_tokens: 5000, output_tokens: 2000, cost_usd: 0 },
        timestamp: 1700000010,
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].completed).toBe(true);
  });

  it("adds output items from agent_output events", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const outputs = [
      makeEvent({
        event_type: "agent_output",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "", text: "Analyzing code", round: 1 },
      }),
    ];
    const sessions = buildSessions(events, [], outputs, []);
    expect(sessions[0].items).toHaveLength(1);
    expect(sessions[0].items[0].type).toBe("output");
    expect((sessions[0].items[0] as { text: string }).text).toBe("Analyzing code");
  });

  it("adds tool_call items from agent_tool_call events", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const toolCalls = [
      makeEvent({
        event_type: "agent_tool_call",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          tool: "read_file",
          input: { path: "src/main.py" },
          type: "call",
          round: 1,
        },
      }),
    ];
    const sessions = buildSessions(events, toolCalls, [], []);
    expect(sessions[0].items).toHaveLength(1);
    expect(sessions[0].items[0].type).toBe("tool_call");
    expect((sessions[0].items[0] as { tool: string }).tool).toBe("read_file");
  });

  it("adds tool_result items for subtype 'result'", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const toolCalls = [
      makeEvent({
        event_type: "agent_tool_call",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          tool: "read_file",
          result: "file contents here",
          type: "result",
          round: 1,
        },
      }),
    ];
    const sessions = buildSessions(events, toolCalls, [], []);
    expect(sessions[0].items).toHaveLength(1);
    expect(sessions[0].items[0].type).toBe("tool_result");
    expect((sessions[0].items[0] as { result: string }).result).toBe("file contents here");
  });

  it("creates both tool_call and tool_result for legacy events with result_snippet", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const toolCalls = [
      makeEvent({
        event_type: "agent_tool_call",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          tool: "read_file",
          input: { path: "src/main.py" },
          result_snippet: "truncated contents...",
          round: 1,
        },
      }),
    ];
    const sessions = buildSessions(events, toolCalls, [], []);
    expect(sessions[0].items).toHaveLength(2);
    expect(sessions[0].items[0].type).toBe("tool_call");
    expect(sessions[0].items[1].type).toBe("tool_result");
    expect((sessions[0].items[1] as { result: string }).result).toBe("truncated contents...");
  });

  it("handles multiple sessions (different roles in same stage)", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "review",
        data: { role: "security_reviewer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_started",
        stage: "review",
        data: { role: "quality_reviewer", repo: "" },
        timestamp: 1700000001,
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions).toHaveLength(2);
    expect(sessions[0].role).toBe("security_reviewer");
    expect(sessions[1].role).toBe("quality_reviewer");
  });

  it("handles multiple repos (same role, different repos)", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "backend" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "frontend" },
        timestamp: 1700000001,
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions).toHaveLength(2);
    expect(sessions[0].repo).toBe("backend");
    expect(sessions[1].repo).toBe("frontend");
  });

  it("sorts events by timestamp", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
    ];
    const outputs = [
      makeEvent({
        event_type: "agent_output",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "", text: "second", round: 2 },
        timestamp: 1700000002,
      }),
      makeEvent({
        event_type: "agent_output",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "", text: "first", round: 1 },
        timestamp: 1700000001,
      }),
    ];
    const sessions = buildSessions(events, [], outputs, []);
    expect((sessions[0].items[0] as { text: string }).text).toBe("first");
    expect((sessions[0].items[1] as { text: string }).text).toBe("second");
  });

  it("sets token/cost info from agent_completed", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          input_tokens: 5000,
          output_tokens: 2000,
          cost_usd: 0.05,
          round_count: 3,
          throttle_count: 1,
          throttle_seconds: 5.2,
        },
        timestamp: 1700000010,
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions[0].inputTokens).toBe(5000);
    expect(sessions[0].outputTokens).toBe(2000);
    expect(sessions[0].costUsd).toBe(0.05);
    expect(sessions[0].roundCount).toBe(3);
    expect(sessions[0].throttleCount).toBe(1);
    expect(sessions[0].throttleSeconds).toBe(5.2);
  });

  it("handles orphaned agent_completed (no prior agent_started)", () => {
    const events = [
      makeEvent({
        event_type: "agent_completed",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          input_tokens: 1000,
          output_tokens: 500,
          cost_usd: 0.01,
        },
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].completed).toBe(true);
    expect(sessions[0].inputTokens).toBe(1000);
  });

  it("handles events with missing/empty data fields", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "", repo: "" },
      }),
    ];
    const outputs = [
      makeEvent({
        event_type: "agent_output",
        stage: "tdd",
        data: { role: "", text: "" },
      }),
    ];
    const sessions = buildSessions(events, [], outputs, []);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].role).toBe("");
    expect(sessions[0].repo).toBe("");
    expect(sessions[0].items).toHaveLength(1);
    expect((sessions[0].items[0] as { text: string }).text).toBe("");
  });

  it("extracts modelBreakdown from agent_completed", () => {
    const breakdown = {
      "claude-3-5-sonnet-20241022": {
        input_tokens: 3000,
        output_tokens: 1500,
        cost_usd: 0.03,
        throttle_count: 0,
        throttle_seconds: 0,
        api_calls: 0,
      },
      "claude-3-haiku-20240307": {
        input_tokens: 2000,
        output_tokens: 500,
        cost_usd: 0.002,
        throttle_count: 1,
        throttle_seconds: 3.5,
        api_calls: 0,
      },
    };
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          input_tokens: 5000,
          output_tokens: 2000,
          cost_usd: 0.032,
          model_breakdown: breakdown,
        },
        timestamp: 1700000010,
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].modelBreakdown).toEqual(breakdown);
    expect(sessions[0].modelBreakdown["claude-3-5-sonnet-20241022"].cost_usd).toBe(0.03);
    expect(sessions[0].modelBreakdown["claude-3-haiku-20240307"].throttle_count).toBe(1);
  });

  it("defaults modelBreakdown to empty object when not provided", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          input_tokens: 1000,
          output_tokens: 500,
          cost_usd: 0,
        },
        timestamp: 1700000010,
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions[0].modelBreakdown).toEqual({});
  });

  it("stores models array from agent_started", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: {
          role: "tdd_developer",
          repo: "",
          models: ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
        },
      }),
    ];
    const sessions = buildSessions(events, [], [], []);
    expect(sessions[0].models).toEqual(["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]);
  });

  it("adds nudge items from agent_nudge events", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const nudges = [
      makeEvent({
        event_type: "agent_nudge",
        stage: "tdd",
        data: { role: "tdd_developer", repo: "", text: "focus on edge cases" },
      }),
    ];
    const sessions = buildSessions(events, [], [], nudges);
    expect(sessions[0].items).toHaveLength(1);
    expect(sessions[0].items[0].type).toBe("nudge");
    expect((sessions[0].items[0] as { text: string }).text).toBe("focus on edge cases");
  });
});
