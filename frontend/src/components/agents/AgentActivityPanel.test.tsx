import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AgentActivityPanel from "./AgentActivityPanel";
import { makeEvent } from "../../test-utils";

vi.mock("../../api/client", () => ({
  sendNudge: vi.fn().mockResolvedValue({ status: "nudge_set" }),
}));

describe("AgentActivityPanel", () => {
  it("shows empty state when no activity", () => {
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={[]}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="running"
      />,
    );
    expect(screen.getByText(/no agent activity yet/i)).toBeInTheDocument();
  });

  it("shows agent session in sidebar", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "backend" },
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="running"
      />,
    );
    // "tdd developer" appears in both sidebar and session header
    const matches = screen.getAllByText("tdd developer");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("shows agent output text", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const agentOutputs = [
      makeEvent({
        event_type: "agent_output",
        data: { role: "tdd_developer", repo: "", text: "Analyzing the codebase now" },
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={[]}
        agentOutputs={agentOutputs}
        agentNudges={[]}
        pipelineStatus="running"
      />,
    );
    expect(
      screen.getByText("Analyzing the codebase now"),
    ).toBeInTheDocument();
  });

  it("shows tool call in conversation", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    const toolCalls = [
      makeEvent({
        event_type: "agent_tool_call",
        data: {
          role: "tdd_developer",
          repo: "",
          tool: "read_file",
          input: { path: "src/main.py" },
          type: "call",
        },
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={toolCalls}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="running"
      />,
    );
    // RichToolCall renders read_file as a file path pill
    expect(screen.getByText("src/main.py")).toBeInTheDocument();
  });

  it("shows thinking state for active agent", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="running"
      />,
    );
    expect(screen.getByText(/agent is thinking/i)).toBeInTheDocument();
  });

  it("shows token info for completed agent", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        data: {
          role: "tdd_developer",
          repo: "",
          input_tokens: 5000,
          output_tokens: 2000,
          cost_usd: 0.05,
          round_count: 3,
        },
        timestamp: 1700000010,
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="completed"
      />,
    );
    expect(screen.getByText(/5\.0k.*2\.0k tok/)).toBeInTheDocument();
    expect(screen.getByText("$0.050")).toBeInTheDocument();
  });

  it("shows nudge input for active agent", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "" },
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="running"
      />,
    );
    expect(
      screen.getByPlaceholderText(/guide this agent/i),
    ).toBeInTheDocument();
  });

  it("does not show nudge input for completed agent", () => {
    const events = [
      makeEvent({
        event_type: "agent_started",
        data: { role: "tdd_developer", repo: "" },
        timestamp: 1700000000,
      }),
      makeEvent({
        event_type: "agent_completed",
        data: { role: "tdd_developer", repo: "", input_tokens: 1000, output_tokens: 500 },
        timestamp: 1700000010,
      }),
    ];
    render(
      <AgentActivityPanel
        crId="cr-1"
        events={events}
        toolCalls={[]}
        agentOutputs={[]}
        agentNudges={[]}
        pipelineStatus="completed"
      />,
    );
    expect(
      screen.queryByPlaceholderText(/guide this agent/i),
    ).not.toBeInTheDocument();
  });
});
