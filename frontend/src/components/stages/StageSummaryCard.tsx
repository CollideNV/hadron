import type { PipelineEvent, PipelineEventMap } from "../../api/types";
import type { AgentSession } from "../agents/types";
import { getStageColor } from "../../utils/stages";
import { formatDuration, formatModelName } from "../../utils/format";

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

  // Model breakdown
  const modelSet = new Set<string>();
  for (const s of sessions) {
    if (s.models) s.models.forEach((m) => modelSet.add(m));
    else if (s.model) modelSet.add(s.model);
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
            <span className="text-accent font-mono">${totalCost.toFixed(3)}</span>
          </div>
        )}

        {/* Model badges */}
        {modelSet.size > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-text-dim text-[10px]">Models:</span>
            {Array.from(modelSet).map((m) => (
              <span
                key={m}
                className="text-[9px] text-text-muted font-mono bg-bg-surface border border-border-subtle rounded px-1 py-0.5"
              >
                {formatModelName(m)}
              </span>
            ))}
          </div>
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
              {["critical", "major", "minor", "info"].map(
                (sev) =>
                  sevCounts[sev] && (
                    <span
                      key={sev}
                      className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${
                        sev === "critical"
                          ? "bg-severity-critical/10 text-severity-critical"
                          : sev === "major"
                            ? "bg-severity-major/10 text-severity-major"
                            : sev === "minor"
                              ? "bg-severity-minor/10 text-severity-minor"
                              : "bg-severity-info/10 text-severity-info"
                      }`}
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

