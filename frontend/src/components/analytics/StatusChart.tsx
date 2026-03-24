import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { STATUS_COLORS, CHART_TOOLTIP_STYLE } from "./chartTheme";

export default function StatusChart({ statusCounts }: { statusCounts: Record<string, number> }) {
  const statusEntries = Object.entries(statusCounts);
  const pieData = statusEntries.map(([status, count]) => ({
    name: status,
    value: count,
    fill: STATUS_COLORS[status] || "#455560",
  }));

  return (
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
            <Tooltip {...CHART_TOOLTIP_STYLE} />
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
  );
}
