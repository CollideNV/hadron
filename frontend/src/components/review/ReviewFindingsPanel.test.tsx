import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ReviewFindingsPanel from "./ReviewFindingsPanel";
import type { PipelineEvent } from "../../api/types";

function makeFinding(
  severity: string,
  message: string,
  file?: string,
  line?: number,
): PipelineEvent {
  return {
    cr_id: "cr-1",
    event_type: "review_finding",
    stage: "review",
    data: { severity, message, ...(file ? { file } : {}), ...(line ? { line } : {}) },
    timestamp: 1700000000,
  };
}

describe("ReviewFindingsPanel", () => {
  it("shows empty state when no findings", () => {
    render(<ReviewFindingsPanel findings={[]} />);
    expect(screen.getByText(/no review findings yet/i)).toBeInTheDocument();
  });

  it("shows finding count in header", () => {
    render(
      <ReviewFindingsPanel
        findings={[
          makeFinding("major", "Missing null check"),
          makeFinding("minor", "Naming convention"),
        ]}
      />,
    );
    expect(screen.getByText("(2)")).toBeInTheDocument();
  });

  it("renders findings grouped by severity", () => {
    render(
      <ReviewFindingsPanel
        findings={[
          makeFinding("critical", "SQL injection"),
          makeFinding("minor", "Typo in variable"),
          makeFinding("major", "Missing error handling"),
        ]}
      />,
    );

    const severityLabels = screen.getAllByText(/^(critical|major|minor|info)$/i);
    // critical should appear before major, major before minor
    const texts = severityLabels.map((el) => el.textContent?.toLowerCase());
    expect(texts.indexOf("critical")).toBeLessThan(texts.indexOf("major")!);
    expect(texts.indexOf("major")).toBeLessThan(texts.indexOf("minor")!);
  });

  it("shows file and line when present", () => {
    render(
      <ReviewFindingsPanel
        findings={[makeFinding("major", "Bug here", "src/app.py", 42)]}
      />,
    );
    expect(screen.getByText("src/app.py:42")).toBeInTheDocument();
  });

  it("shows message text", () => {
    render(
      <ReviewFindingsPanel
        findings={[makeFinding("info", "Consider adding docstring")]}
      />,
    );
    expect(
      screen.getByText("Consider adding docstring"),
    ).toBeInTheDocument();
  });

  it("shows 'No message' for empty message", () => {
    const finding: PipelineEvent = {
      cr_id: "cr-1",
      event_type: "review_finding",
      stage: "review",
      data: { severity: "info", message: "" },
      timestamp: 1700000000,
    };
    render(<ReviewFindingsPanel findings={[finding]} />);
    expect(screen.getByText("No message")).toBeInTheDocument();
  });
});
