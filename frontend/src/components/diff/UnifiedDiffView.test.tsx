import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import UnifiedDiffView from "./UnifiedDiffView";
import type { StageDiffData } from "../../api/types";

function makeDiffData(overrides: Partial<StageDiffData> = {}): StageDiffData {
  return {
    diff: "",
    diff_truncated: false,
    ...overrides,
  };
}

describe("UnifiedDiffView", () => {
  it("renders stats bar", () => {
    const data = makeDiffData({
      diff: "diff --git a/foo.py b/foo.py\n+line\n-old",
      stats: { files_changed: 1, insertions: 1, deletions: 1 },
    });
    render(<UnifiedDiffView data={data} />);
    expect(screen.getByText("1 file changed")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
  });

  it("renders file headers", () => {
    const data = makeDiffData({
      diff: "diff --git a/src/app.py b/src/app.py\n@@ -1,3 +1,4 @@\n context\n+added line",
    });
    render(<UnifiedDiffView data={data} />);
    expect(screen.getByText("src/app.py")).toBeInTheDocument();
  });

  it("renders additions and deletions with correct markers", () => {
    const data = makeDiffData({
      diff: "diff --git a/f.py b/f.py\n+new line\n-old line",
    });
    render(<UnifiedDiffView data={data} />);
    expect(screen.getByText("+")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("shows truncation warning", () => {
    const data = makeDiffData({ diff_truncated: true });
    render(<UnifiedDiffView data={data} />);
    expect(screen.getByText(/truncated/i)).toBeInTheDocument();
  });

  it("shows 'No diff available' when diff is empty", () => {
    const data = makeDiffData({ diff: "" });
    render(<UnifiedDiffView data={data} />);
    expect(screen.getByText("No diff available")).toBeInTheDocument();
  });

  it("collapses file section on click", () => {
    const data = makeDiffData({
      diff: "diff --git a/f.py b/f.py\n+added line content here",
    });
    render(<UnifiedDiffView data={data} />);
    expect(screen.getByText("added line content here")).toBeInTheDocument();
    fireEvent.click(screen.getByText("f.py"));
    expect(screen.queryByText("added line content here")).not.toBeInTheDocument();
  });
});
