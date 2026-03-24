import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { CHART_TOOLTIP_STYLE } from "./chartTheme";
import type { StageDuration } from "../../api/types";

export default function StageDurationChart({ stageDurations }: { stageDurations: StageDuration[] }) {
  if (stageDurations.length === 0) return null;

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="analytics-stage-durations">
      <h2 className="text-[10px] text-text-dim uppercase tracking-wider mb-3">Average Stage Duration</h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={stageDurations} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 80 }}>
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
            {...CHART_TOOLTIP_STYLE}
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
  );
}
