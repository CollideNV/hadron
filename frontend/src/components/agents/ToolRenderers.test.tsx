import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import RichToolCall from "./ToolRenderers";
import type { ConversationItem } from "./types";

type ToolCallItem = Extract<ConversationItem, { type: "tool_call" }>;
type ToolResultItem = Extract<ConversationItem, { type: "tool_result" }>;

function makeCall(tool: string, input: Record<string, unknown>): ToolCallItem {
  return { type: "tool_call", tool, input, round: 1, ts: 1700000000 };
}

function makeResult(tool: string, result: string): ToolResultItem {
  return { type: "tool_result", tool, result, round: 1, ts: 1700000001 };
}

describe("RichToolCall", () => {
  it("renders read_file with file path pill", () => {
    const call = makeCall("read_file", { path: "src/main.py" });
    const result = makeResult("read_file", "import os\nprint('hello')");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("src/main.py")).toBeInTheDocument();
  });

  it("renders read_file content with line numbers", () => {
    const call = makeCall("read_file", { path: "src/main.py" });
    const result = makeResult("read_file", "line1\nline2\nline3");
    render(<RichToolCall call={call} result={result} />);
    // Collapsed by default — expand to see content
    fireEvent.click(screen.getByText("expand"));
    expect(screen.getByText(/1 \| line1/)).toBeInTheDocument();
    expect(screen.getByText(/3 \| line3/)).toBeInTheDocument();
  });

  it("renders write_file with green accent and path", () => {
    const call = makeCall("write_file", {
      path: "src/new_file.py",
      content: "print('created')",
    });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("src/new_file.py")).toBeInTheDocument();
    // Collapsed by default — expand to see content
    fireEvent.click(screen.getByText("expand"));
    expect(screen.getByText("print('created')")).toBeInTheDocument();
  });

  it("renders run_command with terminal style", () => {
    const call = makeCall("run_command", { command: "pytest tests/" });
    const result = makeResult("run_command", "3 passed\nexit code: 0");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("pytest tests/")).toBeInTheDocument();
    expect(screen.getByText("exit 0")).toBeInTheDocument();
  });

  it("renders run_command with failing exit code", () => {
    const call = makeCall("run_command", { command: "npm test" });
    const result = makeResult("run_command", "FAIL\nexit code: 1");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("exit 1")).toBeInTheDocument();
  });

  it("renders search_files with match count", () => {
    const call = makeCall("search_files", { pattern: "TODO" });
    const result = makeResult(
      "search_files",
      "src/a.py:10: TODO fix this\nsrc/b.py:5: TODO later",
    );
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("TODO")).toBeInTheDocument();
    expect(screen.getByText(/2 matches/)).toBeInTheDocument();
  });

  it("renders list_directory collapsed by default", () => {
    const call = makeCall("list_directory", { path: "src/" });
    const result = makeResult("list_directory", "main.py\nutils.py");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("src/")).toBeInTheDocument();
    // Content is collapsed by default
    expect(screen.queryByText("main.py")).not.toBeInTheDocument();
  });

  it("renders list_directory content when expanded", () => {
    const call = makeCall("list_directory", { path: "src/" });
    const result = makeResult("list_directory", "main.py\nutils.py");
    render(<RichToolCall call={call} result={result} />);
    fireEvent.click(screen.getByText("expand"));
    expect(screen.getByText(/main\.py/)).toBeInTheDocument();
  });

  it("renders fallback for unknown tool with key-value pairs", () => {
    const call = makeCall("custom_tool", { foo: "bar", baz: 42 });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("custom_tool")).toBeInTheDocument();
    // Collapsed by default, but summary shows in button
    expect(screen.getByText(/foo: bar/)).toBeInTheDocument();
  });

  /* ── Edge cases: malformed inputs ── */

  it("renders read_file with missing path gracefully", () => {
    const call = makeCall("read_file", {});
    render(<RichToolCall call={call} />);
    // Should render without crashing — collapsed by default
    expect(screen.getByText("expand")).toBeInTheDocument();
  });

  it("renders write_file with missing path and content", () => {
    const call = makeCall("write_file", {});
    render(<RichToolCall call={call} />);
    // Collapsed by default — expand to see content
    fireEvent.click(screen.getByText("expand"));
    expect(screen.getByText("(empty)")).toBeInTheDocument();
  });

  it("renders run_command with missing command string", () => {
    const call = makeCall("run_command", {});
    render(<RichToolCall call={call} />);
    // Should render the terminal style without crashing
    expect(screen.getByText("$")).toBeInTheDocument();
  });

  it("renders search_files with missing pattern", () => {
    const call = makeCall("search_files", {});
    const result = makeResult("search_files", "match1\nmatch2");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText(/2 matches/)).toBeInTheDocument();
  });

  it("renders read_file with file_path instead of path", () => {
    const call = makeCall("read_file", { file_path: "alt/path.ts" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("alt/path.ts")).toBeInTheDocument();
  });

  it("renders run_command using cmd key", () => {
    const call = makeCall("run_command", { cmd: "ls -la" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("ls -la")).toBeInTheDocument();
  });

  it("renders bash tool (alias for run_command)", () => {
    const call = makeCall("bash", { command: "echo hello" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("echo hello")).toBeInTheDocument();
  });

  it("renders execute_command tool (alias for run_command)", () => {
    const call = makeCall("execute_command", { command: "npm build" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("npm build")).toBeInTheDocument();
  });

  it("renders grep tool (alias for search_files)", () => {
    const call = makeCall("grep", { regex: "pattern" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("pattern")).toBeInTheDocument();
  });

  /* ── extractExitCode edge formats ── */

  it("extracts exit code from 'exit_code: N' format", () => {
    const call = makeCall("run_command", { command: "test" });
    const result = makeResult("run_command", "output\nexit_code: 2");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("exit 2")).toBeInTheDocument();
  });

  it("extracts exit code from 'exit N' at end of output", () => {
    const call = makeCall("run_command", { command: "test" });
    const result = makeResult("run_command", "some output\nexit 42");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText("exit 42")).toBeInTheDocument();
  });

  it("shows no exit code badge when result has no exit code", () => {
    const call = makeCall("run_command", { command: "echo hi" });
    const result = makeResult("run_command", "hi");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.queryByText(/exit \d+/)).not.toBeInTheDocument();
  });

  it("renders tool call without result", () => {
    const call = makeCall("run_command", { command: "pending..." });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("pending...")).toBeInTheDocument();
    // No exit code badge
    expect(screen.queryByText(/exit \d+/)).not.toBeInTheDocument();
  });

  it("renders fallback with empty input object", () => {
    const call = makeCall("custom_tool", {});
    render(<RichToolCall call={call} />);
    expect(screen.getByText("custom_tool")).toBeInTheDocument();
  });

  it("renders fallback with long values truncated in summary", () => {
    const call = makeCall("custom_tool", {
      content: "a".repeat(100),
    });
    render(<RichToolCall call={call} />);
    expect(screen.getByText(/content: a{50}\.\.\./)).toBeInTheDocument();
  });

  it("renders search_files with query key", () => {
    const call = makeCall("search_files", { query: "findme" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("findme")).toBeInTheDocument();
  });

  it("renders list_directory with directory key", () => {
    const call = makeCall("list_directory", { directory: "/tmp" });
    render(<RichToolCall call={call} />);
    expect(screen.getByText("/tmp")).toBeInTheDocument();
  });

  it("counts matches correctly for single match", () => {
    const call = makeCall("search_files", { pattern: "x" });
    const result = makeResult("search_files", "one match");
    render(<RichToolCall call={call} result={result} />);
    expect(screen.getByText(/1 match$/)).toBeInTheDocument();
  });
});
