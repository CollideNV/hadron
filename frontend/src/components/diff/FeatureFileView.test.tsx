import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FeatureFileView from "./FeatureFileView";
import type { StageDiffFile } from "../../api/types";

describe("FeatureFileView", () => {
  it("renders file path headers", () => {
    const files: StageDiffFile[] = [
      { path: "features/login.feature", content: "Feature: Login" },
    ];
    render(<FeatureFileView files={files} />);
    expect(screen.getByText("features/login.feature")).toBeInTheDocument();
  });

  it("highlights Gherkin keywords", () => {
    const files: StageDiffFile[] = [
      {
        path: "test.feature",
        content: "Feature: Test\n  Scenario: Example\n    Given something\n    When action\n    Then result",
      },
    ];
    render(<FeatureFileView files={files} />);
    expect(screen.getByText("Given")).toBeInTheDocument();
    expect(screen.getByText("When")).toBeInTheDocument();
    expect(screen.getByText("Then")).toBeInTheDocument();
  });

  it("shows line numbers", () => {
    const files: StageDiffFile[] = [
      { path: "f.feature", content: "line1\nline2\nline3" },
    ];
    render(<FeatureFileView files={files} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows truncation warning", () => {
    const files: StageDiffFile[] = [
      { path: "f.feature", content: "Feature: Test" },
    ];
    render(<FeatureFileView files={files} truncated />);
    expect(screen.getByText(/truncated/i)).toBeInTheDocument();
  });

  it("shows 'No feature files' when empty", () => {
    render(<FeatureFileView files={[]} />);
    expect(screen.getByText("No feature files")).toBeInTheDocument();
  });

  it("collapses file section on click", () => {
    const files: StageDiffFile[] = [
      { path: "f.feature", content: "Feature: Test" },
    ];
    render(<FeatureFileView files={files} />);
    expect(screen.getByText("Feature: Test")).toBeInTheDocument();
    fireEvent.click(screen.getByText("f.feature"));
    expect(screen.queryByText("Feature: Test")).not.toBeInTheDocument();
  });
});
