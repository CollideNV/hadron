import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ToolCallRow from "./ToolCallRow";
import { makeEvent } from "../../test-utils";

function toolEvent(overrides: Record<string, unknown> = {}) {
  return makeEvent({
    event_type: "agent_tool_call",
    stage: "tdd",
    data: { tool: "write_file", input: { path: "src/main.ts" }, ...overrides },
  });
}

describe("ToolCallRow", () => {
  it("renders tool name and truncated input", () => {
    render(<ToolCallRow event={toolEvent()} color="#37e284" />);
    expect(screen.getByText("write_file")).toBeInTheDocument();
    expect(screen.getByText(/src\/main\.ts/)).toBeInTheDocument();
  });

  it("shows + indicator when collapsed", () => {
    render(<ToolCallRow event={toolEvent()} color="#37e284" />);
    expect(screen.getByText("+")).toBeInTheDocument();
  });

  it("expands to show full input on click", async () => {
    const user = userEvent.setup();
    render(<ToolCallRow event={toolEvent()} color="#37e284" />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Input:")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("shows result snippet when expanded and result_snippet exists", async () => {
    const user = userEvent.setup();
    const event = toolEvent({ result_snippet: "File written successfully" });
    render(<ToolCallRow event={event} color="#37e284" />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Result:")).toBeInTheDocument();
    expect(screen.getByText("File written successfully")).toBeInTheDocument();
  });

  it("does not show result section when no result_snippet", async () => {
    const user = userEvent.setup();
    render(<ToolCallRow event={toolEvent()} color="#37e284" />);
    await user.click(screen.getByRole("button"));
    expect(screen.queryByText("Result:")).not.toBeInTheDocument();
  });

  it("collapses on second click", async () => {
    const user = userEvent.setup();
    render(<ToolCallRow event={toolEvent()} color="#37e284" />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Input:")).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(screen.queryByText("Input:")).not.toBeInTheDocument();
  });

  it("applies the color prop to the tool name", () => {
    render(<ToolCallRow event={toolEvent()} color="#ff0000" />);
    const toolName = screen.getByText("write_file");
    expect(toolName).toHaveStyle({ color: "#ff0000" });
  });

  it("handles empty input gracefully", () => {
    const event = makeEvent({
      event_type: "agent_tool_call",
      stage: "tdd",
      data: { tool: "read_file" },
    });
    render(<ToolCallRow event={event} color="#37e284" />);
    expect(screen.getByText("read_file")).toBeInTheDocument();
  });

  it("truncates long input to 60 chars in collapsed view", () => {
    const longPath = "a".repeat(100);
    const event = toolEvent({ input: { path: longPath } });
    render(<ToolCallRow event={event} color="#37e284" />);
    // The collapsed input is JSON.stringify(input).slice(0, 60)
    const truncated = JSON.stringify({ path: longPath }).slice(0, 60);
    expect(screen.getByText(truncated)).toBeInTheDocument();
  });
});
