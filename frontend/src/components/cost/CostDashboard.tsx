import type { CostBreakdown } from "../../hooks/useCostBreakdown";
import { formatCost, formatTokenPair, formatModelName } from "../../utils/format";
import CostSparkline from "./CostSparkline";

interface CostDashboardProps {
  breakdown: CostBreakdown;
}

export default function CostDashboard({ breakdown }: CostDashboardProps) {
  const { totalCostUsd, byStage, byModel, timeline } = breakdown;

  if (byStage.length === 0) {
    return (
      <p className="text-text-dim text-sm py-4 text-center">
        No cost data yet — costs appear as agents complete work.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {/* Total cost header */}
      <div className="text-center">
        <span className="text-[10px] text-text-dim uppercase tracking-wider">
          Total Pipeline Cost
        </span>
        <div className="font-mono text-2xl text-accent font-semibold mt-0.5">
          {formatCost(totalCostUsd)}
        </div>
      </div>

      {/* Sparkline */}
      {timeline.length >= 2 && (
        <div>
          <h3 className="text-[10px] text-text-dim uppercase tracking-wider mb-2">
            Cost Over Time
          </h3>
          <CostSparkline points={timeline} />
        </div>
      )}

      {/* Cost by stage */}
      <div>
        <h3 className="text-[10px] text-text-dim uppercase tracking-wider mb-2">
          By Stage
        </h3>
        <div className="border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-card text-text-dim text-[10px] uppercase tracking-wider">
                <th className="text-left px-3 py-1.5 font-medium">Stage</th>
                <th className="text-right px-3 py-1.5 font-medium">Agents</th>
                <th className="text-right px-3 py-1.5 font-medium">Tokens</th>
                <th className="text-right px-3 py-1.5 font-medium">Cost</th>
                <th className="px-3 py-1.5 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {byStage.map((s) => {
                const pct = totalCostUsd > 0 ? (s.costUsd / totalCostUsd) * 100 : 0;
                return (
                  <tr
                    key={s.stage}
                    className="border-t border-border-subtle hover:bg-bg-card/50 transition-colors"
                  >
                    <td className="px-3 py-1.5 text-text">{s.label}</td>
                    <td className="px-3 py-1.5 text-right text-text-muted font-mono">
                      {s.agentCount}
                    </td>
                    <td className="px-3 py-1.5 text-right text-text-muted font-mono text-[11px]">
                      {formatTokenPair(s.inputTokens, s.outputTokens)}
                    </td>
                    <td className="px-3 py-1.5 text-right text-accent font-mono">
                      {formatCost(s.costUsd)}
                    </td>
                    <td className="px-3 py-1.5">
                      <div className="h-1.5 bg-bg-card rounded-full overflow-hidden">
                        <div
                          className="h-full bg-accent/60 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cost by model */}
      {byModel.length > 0 && (
        <div>
          <h3 className="text-[10px] text-text-dim uppercase tracking-wider mb-2">
            By Model
          </h3>
          <div className="border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-bg-card text-text-dim text-[10px] uppercase tracking-wider">
                  <th className="text-left px-3 py-1.5 font-medium">Model</th>
                  <th className="text-right px-3 py-1.5 font-medium">Calls</th>
                  <th className="text-right px-3 py-1.5 font-medium">Tokens</th>
                  <th className="text-right px-3 py-1.5 font-medium">Cost</th>
                  <th className="px-3 py-1.5 w-24"></th>
                </tr>
              </thead>
              <tbody>
                {byModel.map((m) => {
                  const pct = totalCostUsd > 0 ? (m.costUsd / totalCostUsd) * 100 : 0;
                  return (
                    <tr
                      key={m.model}
                      className="border-t border-border-subtle hover:bg-bg-card/50 transition-colors"
                    >
                      <td className="px-3 py-1.5 text-text font-mono text-[11px]">
                        {formatModelName(m.model)}
                      </td>
                      <td className="px-3 py-1.5 text-right text-text-muted font-mono">
                        {m.apiCalls}
                      </td>
                      <td className="px-3 py-1.5 text-right text-text-muted font-mono text-[11px]">
                        {formatTokenPair(m.inputTokens, m.outputTokens)}
                      </td>
                      <td className="px-3 py-1.5 text-right text-accent font-mono">
                        {formatCost(m.costUsd)}
                      </td>
                      <td className="px-3 py-1.5">
                        <div className="h-1.5 bg-bg-card rounded-full overflow-hidden">
                          <div
                            className="h-full bg-accent/60 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
