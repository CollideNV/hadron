import { AreaChart, Area, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import type { CostTimelinePoint } from "../../hooks/useCostBreakdown";
import { formatCost } from "../../utils/format";

interface CostSparklineProps {
  points: CostTimelinePoint[];
}

export default function CostSparkline({ points }: CostSparklineProps) {
  if (points.length < 2) return null;

  return (
    <ResponsiveContainer width="100%" height={80}>
      <AreaChart data={points} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <defs>
          <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#37e284" stopOpacity={0.2} />
            <stop offset="100%" stopColor="#37e284" stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Tooltip
          contentStyle={{
            background: "#0a2234",
            border: "1px solid #2a3f4a",
            borderRadius: "6px",
            fontSize: "11px",
            color: "#faf9fe",
          }}
          formatter={(value) => [formatCost(value as number), "Cost"]}
          labelFormatter={() => ""}
        />
        <Area
          type="monotone"
          dataKey="cumulativeCostUsd"
          stroke="#37e284"
          strokeWidth={1.5}
          fill="url(#costGradient)"
          dot={false}
          activeDot={{ r: 3, fill: "#37e284", stroke: "#0a2234", strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
