import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AgentRow from "./AgentRow";
import type { AgentSpan } from "../../utils/buildStageInfos";
import { makeEvent } from "../../test-utils";

function makeAgent(overrides: Partial<AgentSpan> = {}): AgentSpan {
  return {
    role: "spec_writer",
    repo: "my-repo",
    startedAt: 1700000000,
    completedAt: 1700000060,
    toolCalls: [],
    ...overrides,
  };
}

describe("AgentRow", () => {
  it("renders agent role", () => {
    render(<AgentRow agent={makeAgent()} color="#37e284" />);
    expect(screen.getByText("spec_writer")).toBeInTheDocument();
  });

  it("renders repo name when present", () => {
    render(<AgentRow agent={makeAgent({ repo: "frontend" })} color="#37e284" />);
    expect(screen.getByText("frontend")).toBeInTheDocument();
  });

  it("does not render repo when empty string", () => {
    render(<AgentRow agent={makeAgent({ repo: "" })} color="#37e284" />);
    expect(screen.queryByText("frontend")).not.toBeInTheDocument();
  });

  it("shows formatted duration for completed agent", () => {
    const agent = makeAgent({ startedAt: 1700000000, completedAt: 1700000090 });
    render(<AgentRow agent={agent} color="#37e284" />);
    expect(screen.getByText("1m 30s")).toBeInTheDocument();
  });

  it("shows '...' for in-progress agent", () => {
    const agent = makeAgent({ completedAt: null });
    render(<AgentRow agent={agent} color="#37e284" />);
    expect(screen.getByText("...")).toBeInTheDocument();
  });

  it("shows tool count badge", () => {
    const toolCalls = [
      makeEvent({ event_type: "agent_tool_call", data: { role: "spec_writer", tool: "write_file" } }),
      makeEvent({ event_type: "agent_tool_call", data: { role: "spec_writer", tool: "read_file" } }),
    ];
    render(<AgentRow agent={makeAgent({ toolCalls })} color="#37e284" />);
    expect(screen.getByText("2 tools")).toBeInTheDocument();
  });

  it("shows singular 'tool' for one tool call", () => {
    const toolCalls = [
      makeEvent({ event_type: "agent_tool_call", data: { role: "spec_writer", tool: "write_file" } }),
    ];
    render(<AgentRow agent={makeAgent({ toolCalls })} color="#37e284" />);
    expect(screen.getByText("1 tool")).toBeInTheDocument();
  });

  it("does not show tool count when no tools", () => {
    render(<AgentRow agent={makeAgent({ toolCalls: [] })} color="#37e284" />);
    expect(screen.queryByText(/tool/)).not.toBeInTheDocument();
  });

  it("expands to show tool calls on click", async () => {
    const user = userEvent.setup();
    const toolCalls = [
      makeEvent({
        event_type: "agent_tool_call",
        data: { role: "spec_writer", tool: "write_file", input: { path: "foo.ts" } },
      }),
    ];
    render(<AgentRow agent={makeAgent({ toolCalls })} color="#37e284" />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("write_file")).toBeInTheDocument();
  });

  it("does not show tool list when expanded but no tools", async () => {
    const user = userEvent.setup();
    render(<AgentRow agent={makeAgent({ toolCalls: [] })} color="#37e284" />);
    await user.click(screen.getByRole("button"));
    // No tool rows should appear
    expect(screen.queryByText("write_file")).not.toBeInTheDocument();
  });

  it("shows + when collapsed and - when expanded", async () => {
    const user = userEvent.setup();
    render(<AgentRow agent={makeAgent()} color="#37e284" />);
    expect(screen.getByText("+")).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("-")).toBeInTheDocument();
  });
});
