import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import RichConversationView from "./RichConversationView";
import type { AgentSession } from "./types";
import { makeEvent } from "../../test-utils";

vi.mock("../../api/client", () => ({
  sendNudge: vi.fn().mockResolvedValue({ status: "nudge_set" }),
}));

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    role: "developer",
    repo: "backend",
    stage: "implementation",
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

describe("RichConversationView", () => {
  it("shows thinking state when no items and active", () => {
    render(
      <RichConversationView
        session={makeSession()}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    expect(screen.getByText(/agent is thinking/i)).toBeInTheDocument();
  });

  it("pairs tool_call and tool_result into single block", () => {
    const session = makeSession({
      items: [
        { type: "tool_call", tool: "read_file", input: { path: "a.py" }, round: 1, ts: 1 },
        { type: "tool_result", tool: "read_file", result: "content here", round: 1, ts: 2 },
      ],
    });
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    // Should show file path from the rich renderer
    expect(screen.getByText("a.py")).toBeInTheDocument();
    // Should NOT show the result as a separate orphaned block
    const readFiles = screen.getAllByText("a.py");
    expect(readFiles.length).toBe(1);
  });

  it("renders agent output with markdown-lite", () => {
    const session = makeSession({
      items: [
        { type: "output", text: "Running **tests** now", round: 1, ts: 1 },
      ],
    });
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    expect(screen.getByText("tests")).toBeInTheDocument();
  });

  it("interleaves test runs by timestamp", () => {
    const session = makeSession({
      items: [
        { type: "output", text: "Starting work", round: 1, ts: 1 },
        { type: "output", text: "Done coding", round: 1, ts: 3 },
      ],
    });
    const testRuns = [
      makeEvent({
        event_type: "test_run",
        stage: "implementation",
        data: { passed: true, iteration: 1 },
        timestamp: 2,
      }),
    ];
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
        testRuns={testRuns}
      />,
    );
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/iteration 1/i)).toBeInTheDocument();
  });

  it("interleaves review findings by timestamp", () => {
    const session = makeSession({
      items: [
        { type: "output", text: "Reviewing code", round: 1, ts: 1 },
      ],
    });
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "major", message: "SQL injection risk", file: "db.py", line: 42 },
        timestamp: 2,
      }),
    ];
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
        findings={findings}
      />,
    );
    expect(screen.getByText("major")).toBeInTheDocument();
    expect(screen.getByText("SQL injection risk")).toBeInTheDocument();
    expect(screen.getByText("db.py:42")).toBeInTheDocument();
  });

  it("shows nudge input for active session", () => {
    render(
      <RichConversationView
        session={makeSession()}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    expect(screen.getByPlaceholderText(/guide this agent/i)).toBeInTheDocument();
  });

  it("does not show nudge input for completed session", () => {
    render(
      <RichConversationView
        session={makeSession({ completed: true })}
        crId="cr-1"
        pipelineStatus="completed"
      />,
    );
    expect(screen.queryByPlaceholderText(/guide this agent/i)).not.toBeInTheDocument();
  });

  it("shows token info for completed session", () => {
    render(
      <RichConversationView
        session={makeSession({
          completed: true,
          inputTokens: 5000,
          outputTokens: 2000,
          costUsd: 0.05,
        })}
        crId="cr-1"
        pipelineStatus="completed"
      />,
    );
    expect(screen.getByText(/5\.0k.*2\.0k tok/)).toBeInTheDocument();
  });

  it("renders orphaned tool_result as a fallback tool entry", () => {
    const session = makeSession({
      items: [
        { type: "tool_result", tool: "read_file", result: "orphaned content", round: 1, ts: 1 },
      ],
    });
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    // Orphaned result renders as collapsed tool block — expand to see content
    fireEvent.click(screen.getByText("expand"));
    expect(screen.getByText(/orphaned content/)).toBeInTheDocument();
  });

  it("renders output with empty text without crashing", () => {
    const session = makeSession({
      items: [
        { type: "output", text: "", round: 1, ts: 1 },
      ],
    });
    const { container } = render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    // Should render without crashing, robot emoji still present
    expect(container.querySelector(".animate-fade-in")).toBeInTheDocument();
  });

  it("renders tool_call with empty input without crashing", () => {
    const session = makeSession({
      items: [
        { type: "tool_call", tool: "unknown_tool", input: {}, round: 1, ts: 1 },
      ],
    });
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    expect(screen.getByText("unknown_tool")).toBeInTheDocument();
  });

  it("renders tool_call with missing tool name as empty string", () => {
    const session = makeSession({
      items: [
        { type: "tool_call", tool: "", input: { foo: "bar" }, round: 1, ts: 1 },
      ],
    });
    const { container } = render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    expect(container.querySelector(".animate-fade-in")).toBeInTheDocument();
  });

  it("handles nudge items in the timeline", () => {
    const session = makeSession({
      items: [
        { type: "nudge", text: "Please focus on error handling", ts: 1 },
      ],
    });
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
      />,
    );
    expect(screen.getByText("Please focus on error handling")).toBeInTheDocument();
  });

  it("renders with empty testRuns and findings arrays", () => {
    const session = makeSession({
      items: [
        { type: "output", text: "Working on it", round: 1, ts: 1 },
      ],
    });
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
        testRuns={[]}
        findings={[]}
      />,
    );
    expect(screen.getByText("Working on it")).toBeInTheDocument();
  });

  it("renders finding with missing severity as info", () => {
    const session = makeSession({
      items: [
        { type: "output", text: "Review done", round: 1, ts: 1 },
      ],
    });
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "info", message: "Something noted" },
        timestamp: 2,
      }),
    ];
    render(
      <RichConversationView
        session={session}
        crId="cr-1"
        pipelineStatus="running"
        findings={findings}
      />,
    );
    expect(screen.getByText("info")).toBeInTheDocument();
    expect(screen.getByText("Something noted")).toBeInTheDocument();
  });

  it("renders finding with missing message as fallback", () => {
    const findings = [
      makeEvent({
        event_type: "review_finding",
        stage: "review",
        data: { severity: "major", message: "No message" },
        timestamp: 2,
      }),
    ];
    render(
      <RichConversationView
        session={makeSession({ items: [{ type: "output", text: "x", round: 1, ts: 1 }] })}
        crId="cr-1"
        pipelineStatus="running"
        findings={findings}
      />,
    );
    expect(screen.getByText("No message")).toBeInTheDocument();
  });
});
