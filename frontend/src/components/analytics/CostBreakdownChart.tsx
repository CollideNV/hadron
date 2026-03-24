import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { CHART_TOOLTIP_STYLE } from "./chartTheme";
import { formatCost } from "../../utils/format";
import type { AnalyticsCost } from "../../api/types";

export type CostTab = "stage" | "model" | "repo" | "day";

interface CostBreakdownChartProps {
  tab: CostTab;
  onTabChange: (tab: CostTab) => void;
  data: AnalyticsCost | null;
  loading: boolean;
}

export default function CostBreakdownChart({ tab, onTabChange, data, loading }: CostBreakdownChartProps) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-cost-breakdown">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[10px] text-text-dim uppercase tracking-wider">Cost Breakdown</h2>
        <div className="flex gap-1">
          {(["stage", "model", "repo", "day"] as CostTab[]).map((t) => (
            <button
              key={t}
              onClick={() => onTabChange(t)}
              data-testid={`cost-tab-${t}`}
              className={`px-2.5 py-1 text-[11px] rounded-md cursor-pointer border transition-colors ${
                tab === t
                  ? "bg-accent/15 text-accent border-accent/30"
                  : "bg-transparent text-text-muted border-border-subtle hover:text-text"
              }`}
            >
              {t === "day" ? "Daily" : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {loading && !data ? (
        <p className="text-text-dim text-sm py-8 text-center">Loading...</p>
      ) : data && data.groups.length > 0 ? (
        <>
          <div className="text-center mb-4">
            <span className="font-mono text-xl text-accent font-semibold">
              {formatCost(data.total_cost_usd)}
            </span>
            <span className="text-text-dim text-xs ml-2">total</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.groups} margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#95a1a8" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#63717a" }}
                tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                axisLine={false}
                tickLine={false}
                width={50}
              />
              <Tooltip
                {...CHART_TOOLTIP_STYLE}
                formatter={(value) => [formatCost(Number(value)), "Cost"]}
              />
              <Bar dataKey="cost_usd" radius={[4, 4, 0, 0]} barSize={28}>
                {data.groups.map((_, i) => (
                  <Cell key={i} fill="#37e284" opacity={0.6 + (i % 3) * 0.13} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </>
      ) : (
        <p className="text-text-dim text-sm py-8 text-center">No cost data for this grouping.</p>
      )}
    </div>
  );
}
