import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AgentSessionList from "./AgentSessionList";
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

describe("AgentSessionList", () => {
  it("renders session role names formatted (underscores to spaces)", () => {
    const sessions = [makeSession({ role: "tdd_developer" })];
    render(
      <AgentSessionList sessions={sessions} selectedIndex={0} onSelect={() => {}} />,
    );
    expect(screen.getByText("tdd developer")).toBeInTheDocument();
  });

  it("calls onSelect with correct index when clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const sessions = [
      makeSession({ role: "spec_writer" }),
      makeSession({ role: "tdd_developer" }),
    ];
    render(
      <AgentSessionList sessions={sessions} selectedIndex={0} onSelect={onSelect} />,
    );
    await user.click(screen.getByText("tdd developer"));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("shows completion indicator (completed vs active)", () => {
    const sessions = [
      makeSession({ role: "spec_writer", completed: true }),
      makeSession({ role: "tdd_developer", completed: false }),
    ];
    const { container } = render(
      <AgentSessionList sessions={sessions} selectedIndex={0} onSelect={() => {}} />,
    );
    const dots = container.querySelectorAll("span.rounded-full");
    expect(dots[0]).toHaveClass("bg-status-completed");
    expect(dots[1]).toHaveClass("bg-accent");
  });

  it("shows model name when present", () => {
    const sessions = [makeSession({ model: "claude-3-5-sonnet-20241022" })];
    render(
      <AgentSessionList sessions={sessions} selectedIndex={0} onSelect={() => {}} />,
    );
    expect(screen.getByText("3-5-sonnet")).toBeInTheDocument();
  });

  it("shows repo name when present", () => {
    const sessions = [makeSession({ repo: "backend" })];
    render(
      <AgentSessionList sessions={sessions} selectedIndex={0} onSelect={() => {}} />,
    );
    expect(screen.getByText(/backend/)).toBeInTheDocument();
  });

  it("handles empty sessions array", () => {
    const { container } = render(
      <AgentSessionList sessions={[]} selectedIndex={0} onSelect={() => {}} />,
    );
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("highlights selected session with bg-accent/10 class", () => {
    const sessions = [
      makeSession({ role: "spec_writer" }),
      makeSession({ role: "tdd_developer" }),
    ];
    const { container } = render(
      <AgentSessionList sessions={sessions} selectedIndex={1} onSelect={() => {}} />,
    );
    const buttons = container.querySelectorAll("button");
    expect(buttons[1].className).toContain("bg-accent/10");
    expect(buttons[0].className).not.toContain("bg-accent/10");
  });
});
