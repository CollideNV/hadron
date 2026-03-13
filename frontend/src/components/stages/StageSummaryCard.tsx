import type { PipelineEvent, PipelineEventMap, ModelBreakdownEntry } from "../../api/types";
import type { AgentSession } from "../agents/types";
import { getStageColor } from "../../utils/stages";
import { SEVERITY_BADGE_CLASSES, SEVERITY_ORDER } from "../../utils/constants";
import { formatDuration, formatModelName, formatTokenPair, formatCost } from "../../utils/format";

export { getStageColor } from "../../utils/stages";

interface StageSummaryCardProps {
  stageName: string;
  events: PipelineEvent[];
  sessions: AgentSession[];
  testRuns: PipelineEvent[];
  findings: PipelineEvent[];
}

export default function StageSummaryCard({
  stageName,
  events,
  sessions,
  testRuns,
  findings,
}: StageSummaryCardProps) {
  const color = getStageColor(stageName);

  // Duration from stage_entered to stage_completed
  const entered = events.find(
    (e) => e.event_type === "stage_entered" && e.stage.split(":")[0] === stageName,
  );
  const completed = events.find(
    (e) => e.event_type === "stage_completed" && e.stage.split(":")[0] === stageName,
  );
  const duration =
    entered && completed
      ? formatDuration(entered.timestamp, completed.timestamp)
      : entered
        ? "running..."
        : null;

  // Cost across sessions
  const totalCost = sessions.reduce((sum, s) => sum + s.costUsd, 0);

  // Aggregate per-model stats across all sessions
  const modelStats: Record<string, ModelBreakdownEntry> = {};
  for (const s of sessions) {
    for (const [model, stats] of Object.entries(s.modelBreakdown)) {
      const existing = modelStats[model];
      if (existing) {
        existing.input_tokens += stats.input_tokens;
        existing.output_tokens += stats.output_tokens;
        existing.cost_usd += stats.cost_usd;
        existing.throttle_count += stats.throttle_count;
        existing.throttle_seconds += stats.throttle_seconds;
        existing.api_calls += stats.api_calls || 0;
      } else {
        modelStats[model] = { ...stats };
      }
    }
  }

  // Test summary
  type TestRunEvent = PipelineEvent & { event_type: "test_run"; data: PipelineEventMap["test_run"] };
  const testsPassed = (testRuns as TestRunEvent[]).filter((t) => t.data.passed).length;
  const testsFailed = testRuns.length - testsPassed;

  // Finding severity counts
  type ReviewFindingEvent = PipelineEvent & { event_type: "review_finding"; data: PipelineEventMap["review_finding"] };
  const sevCounts: Record<string, number> = {};
  for (const f of findings as ReviewFindingEvent[]) {
    const sev = f.data.severity || "info";
    sevCounts[sev] = (sevCounts[sev] || 0) + 1;
  }

  return (
    <div className="px-4 py-3 border-b border-border-subtle">
      {/* Stage name */}
      <h3
        className="text-sm font-semibold mb-2"
        style={{ color }}
      >
        {stageName.replace(/_/g, " ")}
      </h3>

      {/* Stats row */}
      <div className="space-y-1.5 text-[11px]">
        {duration && (
          <div className="flex items-center justify-between">
            <span className="text-text-dim">Duration</span>
            <span className="text-text-muted font-mono">{duration}</span>
          </div>
        )}
        {totalCost > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-text-dim">Cost</span>
            <span className="text-accent font-mono">{formatCost(totalCost, 3)}</span>
          </div>
        )}

        {/* Per-model breakdown table */}
        {Object.keys(modelStats).length > 0 && (
          <table className="w-full text-[10px] mt-1 border-spacing-0" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr className="text-text-dim text-left">
                <th className="font-normal pb-0.5">Model</th>
                <th className="font-normal pb-0.5 text-right">Calls</th>
                <th className="font-normal pb-0.5 text-right">Tokens</th>
                <th className="font-normal pb-0.5 text-right">Cost</th>
                <th className="font-normal pb-0.5 text-right">Throttle</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(modelStats).map(([model, stats]) => (
                <tr key={model}>
                  <td className="font-mono text-text-muted truncate pr-2 py-px" title={model}>
                    {formatModelName(model)}
                  </td>
                  <td className="text-text-dim text-right py-px">
                    {stats.api_calls || 0}
                  </td>
                  <td className="text-text-dim text-right py-px whitespace-nowrap">
                    {formatTokenPair(stats.input_tokens, stats.output_tokens)}
                  </td>
                  <td className="text-accent font-mono text-right py-px whitespace-nowrap">
                    {formatCost(stats.cost_usd, 3)}
                  </td>
                  <td className="text-right py-px whitespace-nowrap">
                    {stats.throttle_count > 0
                      ? <span className="text-status-error">{stats.throttle_seconds.toFixed(0)}s</span>
                      : <span className="text-text-dim">&mdash;</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Test badges */}
        {testRuns.length > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-text-dim">Tests</span>
            <div className="flex items-center gap-1.5">
              {testsPassed > 0 && (
                <span className="text-status-completed text-[10px] font-medium">
                  {testsPassed} passed
                </span>
              )}
              {testsFailed > 0 && (
                <span className="text-status-failed text-[10px] font-medium">
                  {testsFailed} failed
                </span>
              )}
            </div>
          </div>
        )}

        {/* Finding badges */}
        {findings.length > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-text-dim">Findings</span>
            <div className="flex items-center gap-1.5">
              {SEVERITY_ORDER.map(
                (sev) =>
                  sevCounts[sev] && (
                    <span
                      key={sev}
                      className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${SEVERITY_BADGE_CLASSES[sev] || SEVERITY_BADGE_CLASSES.info}`}
                    >
                      {sevCounts[sev]} {sev}
                    </span>
                  ),
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

