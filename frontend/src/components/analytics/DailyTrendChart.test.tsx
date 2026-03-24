import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import DailyTrendChart from "./DailyTrendChart";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="chart-container">{children}</div>,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Area: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
}));

describe("DailyTrendChart", () => {
  it("shows empty message when dailyStats is empty", () => {
    render(<DailyTrendChart dailyStats={[]} />);
    expect(screen.getByText("No trend data available.")).toBeInTheDocument();
  });

  it("renders chart when data is present", () => {
    render(
      <DailyTrendChart
        dailyStats={[
          { date: "2026-03-20", total: 5, completed: 3, failed: 1, cost_usd: 0.5 },
          { date: "2026-03-21", total: 8, completed: 6, failed: 2, cost_usd: 1.0 },
        ]}
      />,
    );

    expect(screen.getByTestId("analytics-trend-chart")).toBeInTheDocument();
    expect(screen.getByTestId("chart-container")).toBeInTheDocument();
    expect(screen.queryByText("No trend data available.")).not.toBeInTheDocument();
  });
});
