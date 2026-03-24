import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import KPICards from "./KPICards";
import type { AnalyticsSummary } from "../../api/types";

function makeSummary(overrides: Partial<AnalyticsSummary> = {}): AnalyticsSummary {
  return {
    total_runs: 42,
    status_counts: { completed: 30, failed: 5 },
    success_rate: 0.857,
    total_cost_usd: 12.5,
    avg_cost_usd: 0.2976,
    stage_durations: [],
    daily_stats: [],
    ...overrides,
  };
}

describe("KPICards", () => {
  it("renders all 4 KPI cards with correct values", () => {
    render(<KPICards summary={makeSummary()} />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("86%")).toBeInTheDocument();
    expect(screen.getByText("$12.5000")).toBeInTheDocument();
    expect(screen.getByText("$0.2976")).toBeInTheDocument();
  });

  it("rounds success rate correctly", () => {
    render(<KPICards summary={makeSummary({ success_rate: 0.804 })} />);
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("shows 0% for zero success rate", () => {
    render(<KPICards summary={makeSummary({ success_rate: 0 })} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("shows 100% for perfect success rate", () => {
    render(<KPICards summary={makeSummary({ success_rate: 1.0 })} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("applies accent class when success_rate >= 0.8", () => {
    const { container } = render(<KPICards summary={makeSummary({ success_rate: 0.85 })} />);
    const accentEl = container.querySelector(".text-accent");
    expect(accentEl).toBeInTheDocument();
    expect(accentEl?.textContent).toBe("85%");
  });

  it("does not apply accent class when success_rate < 0.8", () => {
    render(<KPICards summary={makeSummary({ success_rate: 0.5 })} />);
    // The success rate value should render without accent
    expect(screen.getByText("50%")).toBeInTheDocument();
    // 50% element should not have the accent class
    expect(screen.getByText("50%").className).not.toContain("text-accent");
  });
});
