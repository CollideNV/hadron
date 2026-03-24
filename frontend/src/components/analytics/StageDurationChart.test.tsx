import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import StageDurationChart from "./StageDurationChart";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
}));

describe("StageDurationChart", () => {
  it("returns null when stageDurations is empty", () => {
    const { container } = render(<StageDurationChart stageDurations={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders chart and legend when data is present", () => {
    render(
      <StageDurationChart
        stageDurations={[
          { stage: "implementation", label: "Implementation", avg_seconds: 120, p50_seconds: 100, p95_seconds: 300 },
          { stage: "review", label: "Code Review", avg_seconds: 45, p50_seconds: 40, p95_seconds: 90 },
        ]}
      />,
    );

    expect(screen.getByTestId("analytics-stage-durations")).toBeInTheDocument();
    expect(screen.getByText("Average Stage Duration")).toBeInTheDocument();
    expect(screen.getByText("Average")).toBeInTheDocument();
    expect(screen.getByText("p95")).toBeInTheDocument();
  });
});
