import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AnalyticsPage from "./AnalyticsPage";

const mockGetAnalyticsSummary = vi.fn();
const mockGetAnalyticsCost = vi.fn();

vi.mock("../api/client", () => ({
  getAnalyticsSummary: (...args: unknown[]) => mockGetAnalyticsSummary(...args),
  getAnalyticsCost: (...args: unknown[]) => mockGetAnalyticsCost(...args),
}));

// Stub recharts to avoid SVG rendering in jsdom
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="responsive-container">{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div />,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div />,
  BarChart: ({ children }: { children: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  CartesianGrid: () => <div />,
  Legend: () => <div />,
}));

beforeEach(() => {
  mockGetAnalyticsSummary.mockReset();
  mockGetAnalyticsCost.mockReset();
});

const fakeSummary = {
  total_runs: 42,
  status_counts: { completed: 30, failed: 5, running: 7 },
  success_rate: 0.857,
  total_cost_usd: 12.5,
  avg_cost_usd: 0.2976,
  stage_durations: [],
  daily_stats: [],
};

const fakeCost = {
  group_by: "stage",
  total_cost_usd: 12.5,
  groups: [{ key: "implementation", label: "Implementation", cost_usd: 8.0, runs: 20, tokens: 0 }],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalyticsPage />
    </MemoryRouter>,
  );
}

describe("AnalyticsPage", () => {
  it("shows loading state initially", () => {
    mockGetAnalyticsSummary.mockReturnValue(new Promise(() => {}));
    mockGetAnalyticsCost.mockReturnValue(new Promise(() => {}));

    renderPage();
    expect(screen.getByText("Loading analytics...")).toBeInTheDocument();
  });

  it("renders KPI cards after loading", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(fakeSummary);
    mockGetAnalyticsCost.mockResolvedValue(fakeCost);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("analytics-kpis")).toBeInTheDocument();
    });

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("86%")).toBeInTheDocument();
  });

  it("shows error state when summary fails", async () => {
    mockGetAnalyticsSummary.mockRejectedValue(new Error("API down"));
    mockGetAnalyticsCost.mockResolvedValue(fakeCost);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Failed to load analytics.")).toBeInTheDocument();
    });
  });

  it("switches cost tabs", async () => {
    mockGetAnalyticsSummary.mockResolvedValue(fakeSummary);
    mockGetAnalyticsCost.mockResolvedValue(fakeCost);
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("analytics-kpis")).toBeInTheDocument();
    });

    // Click the "repo" tab
    await user.click(screen.getByTestId("cost-tab-repo"));

    // getAnalyticsCost should have been called with "repo"
    await waitFor(() => {
      expect(mockGetAnalyticsCost).toHaveBeenCalledWith("repo");
    });
  });
});
