import type { CostTimelinePoint } from "../../hooks/useCostBreakdown";
import { formatCost } from "../../utils/format";

interface CostSparklineProps {
  points: CostTimelinePoint[];
}

const W = 480;
const H = 80;
const PAD_X = 40;
const PAD_Y = 8;

export default function CostSparkline({ points }: CostSparklineProps) {
  if (points.length < 2) return null;

  const minT = points[0].timestamp;
  const maxT = points[points.length - 1].timestamp;
  const maxC = points[points.length - 1].cumulativeCostUsd;

  const rangeT = maxT - minT || 1;
  const rangeC = maxC || 1;

  const toX = (t: number) => PAD_X + ((t - minT) / rangeT) * (W - PAD_X * 2);
  const toY = (c: number) => PAD_Y + (1 - c / rangeC) * (H - PAD_Y * 2);

  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.timestamp).toFixed(1)},${toY(p.cumulativeCostUsd).toFixed(1)}`)
    .join(" ");

  // Filled area under curve
  const areaD = `${pathD} L${toX(maxT).toFixed(1)},${toY(0).toFixed(1)} L${toX(minT).toFixed(1)},${toY(0).toFixed(1)} Z`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-20 text-accent"
      preserveAspectRatio="none"
    >
      {/* Filled area */}
      <path d={areaD} fill="currentColor" opacity={0.08} />

      {/* Line */}
      <path d={pathD} fill="none" stroke="currentColor" strokeWidth={1.5} opacity={0.7} />

      {/* Dots */}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={toX(p.timestamp)}
          cy={toY(p.cumulativeCostUsd)}
          r={2.5}
          fill="currentColor"
          opacity={0.9}
        />
      ))}

      {/* Y-axis labels */}
      <text x={PAD_X - 4} y={toY(maxC) + 3} textAnchor="end" className="fill-text-dim text-[8px]">
        {formatCost(maxC, 3)}
      </text>
      <text x={PAD_X - 4} y={toY(0) + 3} textAnchor="end" className="fill-text-dim text-[8px]">
        $0
      </text>
    </svg>
  );
}
