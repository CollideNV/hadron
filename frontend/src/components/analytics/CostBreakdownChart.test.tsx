import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CostBreakdownChart from "./CostBreakdownChart";
import type { AnalyticsCost } from "../../api/types";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Cell: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
}));

const fakeCostData: AnalyticsCost = {
  group_by: "stage",
  total_cost_usd: 5.5,
  groups: [
    { key: "implementation", label: "Implementation", cost_usd: 3.5, runs: 10, tokens: 0 },
    { key: "review", label: "Code Review", cost_usd: 2.0, runs: 8, tokens: 0 },
  ],
};

describe("CostBreakdownChart", () => {
  it("shows loading state", () => {
    render(
      <CostBreakdownChart tab="stage" onTabChange={vi.fn()} data={null} loading={true} />,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows empty state when no groups", () => {
    const emptyData: AnalyticsCost = { group_by: "stage", total_cost_usd: 0, groups: [] };
    render(
      <CostBreakdownChart tab="stage" onTabChange={vi.fn()} data={emptyData} loading={false} />,
    );
    expect(screen.getByText("No cost data for this grouping.")).toBeInTheDocument();
  });

  it("renders total cost and chart when data present", () => {
    render(
      <CostBreakdownChart tab="stage" onTabChange={vi.fn()} data={fakeCostData} loading={false} />,
    );
    expect(screen.getByText("$5.5000")).toBeInTheDocument();
    expect(screen.getByText("total")).toBeInTheDocument();
  });

  it("calls onTabChange when clicking a tab", async () => {
    const onTabChange = vi.fn();
    const user = userEvent.setup();

    render(
      <CostBreakdownChart tab="stage" onTabChange={onTabChange} data={fakeCostData} loading={false} />,
    );

    await user.click(screen.getByTestId("cost-tab-repo"));
    expect(onTabChange).toHaveBeenCalledWith("repo");
  });

  it("highlights active tab", () => {
    render(
      <CostBreakdownChart tab="model" onTabChange={vi.fn()} data={fakeCostData} loading={false} />,
    );

    const modelTab = screen.getByTestId("cost-tab-model");
    expect(modelTab.className).toContain("text-accent");
  });
});
