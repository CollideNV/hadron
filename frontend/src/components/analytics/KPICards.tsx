import type { AnalyticsSummary } from "../../api/types";
import { formatCost } from "../../utils/format";

function KPI({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-4 text-center">
      <div className="text-[10px] text-text-dim uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono text-lg font-semibold ${accent ? "text-accent" : "text-text"}`}>
        {value}
      </div>
    </div>
  );
}

export default function KPICards({ summary }: { summary: AnalyticsSummary }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="analytics-kpis">
      <KPI label="Total Runs" value={String(summary.total_runs)} />
      <KPI label="Success Rate" value={`${Math.round(summary.success_rate * 100)}%`} accent={summary.success_rate >= 0.8} />
      <KPI label="Total Cost" value={formatCost(summary.total_cost_usd)} />
      <KPI label="Avg Cost / Run" value={formatCost(summary.avg_cost_usd)} />
    </div>
  );
}
