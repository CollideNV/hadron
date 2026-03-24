import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusChart from "./StatusChart";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: () => <div />,
  Cell: () => <div />,
  Tooltip: () => <div />,
}));

describe("StatusChart", () => {
  it("renders legend entries for each status", () => {
    render(<StatusChart statusCounts={{ completed: 10, failed: 3, running: 2 }} />);

    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders with empty statusCounts", () => {
    render(<StatusChart statusCounts={{}} />);
    expect(screen.getByTestId("analytics-status-chart")).toBeInTheDocument();
    expect(screen.getByText("Status Distribution")).toBeInTheDocument();
  });
});
