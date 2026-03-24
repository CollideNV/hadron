import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { CHART_TOOLTIP_STYLE } from "./chartTheme";
import type { DailyStat } from "../../api/types";

export default function DailyTrendChart({ dailyStats }: { dailyStats: DailyStat[] }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-trend-chart">
      <h2 className="text-[10px] text-text-dim uppercase tracking-wider mb-3">Daily Runs (14d)</h2>
      {dailyStats.length > 0 ? (
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={dailyStats} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#37e284" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#37e284" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#63717a" }}
              tickFormatter={(d: string) => d.slice(5)}
              axisLine={false}
              tickLine={false}
            />
            <YAxis hide />
            <Tooltip
              {...CHART_TOOLTIP_STYLE}
              formatter={(value, name) => [String(value), name === "completed" ? "Completed" : name === "failed" ? "Failed" : "Total"]}
            />
            <Area type="monotone" dataKey="completed" stroke="#37e284" strokeWidth={1.5} fill="url(#trendGradient)" dot={false} />
            <Area type="monotone" dataKey="failed" stroke="#ff4157" strokeWidth={1} fill="none" dot={false} strokeDasharray="4 4" />
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-text-dim text-sm py-8 text-center">No trend data available.</p>
      )}
    </div>
  );
}
