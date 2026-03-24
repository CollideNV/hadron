import { useState } from "react";
import { useAnalyticsSummary, useAnalyticsCost } from "../hooks/useAnalytics";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie,
} from "recharts";
import { formatCost } from "../utils/format";

const STATUS_COLORS: Record<string, string> = {
  completed: "#37e284",
  running: "#37e284",
  failed: "#ff4157",
  paused: "#f0b832",
  pending: "#455560",
};

const TOOLTIP_STYLE = {
  contentStyle: {
    background: "#0a2234",
    border: "1px solid #2a3f4a",
    borderRadius: "6px",
    fontSize: "12px",
    color: "#faf9fe",
  },
  itemStyle: { color: "#faf9fe" },
};

type CostTab = "stage" | "model" | "repo" | "day";

export default function AnalyticsPage() {
  const { data: summary, loading: summaryLoading } = useAnalyticsSummary();
  const [costTab, setCostTab] = useState<CostTab>("stage");
  const { data: costData, loading: costLoading } = useAnalyticsCost(costTab);

  if (summaryLoading && !summary) {
    return <div className="max-w-6xl mx-auto py-8 px-4 text-text-dim">Loading analytics...</div>;
  }

  if (!summary) {
    return <div className="max-w-6xl mx-auto py-8 px-4 text-text-dim">Failed to load analytics.</div>;
  }

  const statusEntries = Object.entries(summary.status_counts);
  const pieData = statusEntries.map(([status, count]) => ({
    name: status,
    value: count,
    fill: STATUS_COLORS[status] || "#455560",
  }));

  return (
    <div className="max-w-6xl mx-auto py-8 px-4 space-y-6">
      <h1 className="text-lg font-semibold text-text">Analytics</h1>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="analytics-kpis">
        <KPI label="Total Runs" value={String(summary.total_runs)} />
        <KPI label="Success Rate" value={`${Math.round(summary.success_rate * 100)}%`} accent={summary.success_rate >= 0.8} />
        <KPI label="Total Cost" value={formatCost(summary.total_cost_usd)} />
        <KPI label="Avg Cost / Run" value={formatCost(summary.avg_cost_usd)} />
      </div>

      {/* Two-column: Status distribution + Success rate trend */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Status donut */}
        <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-status-chart">
          <h2 className="text-[10px] text-text-dim uppercase tracking-wider mb-3">Status Distribution</h2>
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={140} height={140}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={60}
                  paddingAngle={2}
                  stroke="none"
                >
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip {...TOOLTIP_STYLE} />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-col gap-1.5">
              {statusEntries.map(([status, count]) => (
                <div key={status} className="flex items-center gap-2 text-sm">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ background: STATUS_COLORS[status] || "#455560" }}
                  />
                  <span className="text-text-muted capitalize">{status}</span>
                  <span className="font-mono text-text">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Daily trend */}
        <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-trend-chart">
          <h2 className="text-[10px] text-text-dim uppercase tracking-wider mb-3">Daily Runs (14d)</h2>
          {summary.daily_stats.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={summary.daily_stats} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
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
                  {...TOOLTIP_STYLE}
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
      </div>

      {/* Stage durations */}
      {summary.stage_durations.length > 0 && (
        <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-stage-durations">
          <h2 className="text-[10px] text-text-dim uppercase tracking-wider mb-3">Average Stage Duration</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={summary.stage_durations} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 80 }}>
              <XAxis
                type="number"
                tick={{ fontSize: 10, fill: "#63717a" }}
                tickFormatter={(s: number) => s >= 60 ? `${Math.round(s / 60)}m` : `${s}s`}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 11, fill: "#95a1a8" }}
                axisLine={false}
                tickLine={false}
                width={75}
              />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(value) => { const v = Number(value); return [v >= 60 ? `${(v / 60).toFixed(1)}m` : `${v}s`, "Avg"]; }}
              />
              <Bar dataKey="avg_seconds" fill="#37e284" opacity={0.7} radius={[0, 4, 4, 0]} barSize={14} />
              <Bar dataKey="p95_seconds" fill="#f0b832" opacity={0.35} radius={[0, 4, 4, 0]} barSize={14} />
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2 text-[10px] text-text-dim">
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-accent/70 rounded" /> Average</span>
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-status-paused/35 rounded" /> p95</span>
          </div>
        </div>
      )}

      {/* Cost breakdown */}
      <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-cost-breakdown">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] text-text-dim uppercase tracking-wider">Cost Breakdown</h2>
          <div className="flex gap-1">
            {(["stage", "model", "repo", "day"] as CostTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setCostTab(tab)}
                data-testid={`cost-tab-${tab}`}
                className={`px-2.5 py-1 text-[11px] rounded-md cursor-pointer border transition-colors ${
                  costTab === tab
                    ? "bg-accent/15 text-accent border-accent/30"
                    : "bg-transparent text-text-muted border-border-subtle hover:text-text"
                }`}
              >
                {tab === "day" ? "Daily" : tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {costLoading && !costData ? (
          <p className="text-text-dim text-sm py-8 text-center">Loading...</p>
        ) : costData && costData.groups.length > 0 ? (
          <>
            <div className="text-center mb-4">
              <span className="font-mono text-xl text-accent font-semibold">
                {formatCost(costData.total_cost_usd)}
              </span>
              <span className="text-text-dim text-xs ml-2">total</span>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={costData.groups} margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
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
                  {...TOOLTIP_STYLE}
                  formatter={(value) => [formatCost(Number(value)), "Cost"]}
                />
                <Bar dataKey="cost_usd" radius={[4, 4, 0, 0]} barSize={28}>
                  {costData.groups.map((_, i) => (
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
    </div>
  );
}

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
