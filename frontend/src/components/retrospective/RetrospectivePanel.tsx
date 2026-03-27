import { useEffect, useState } from "react";
import { getRetrospective } from "../../api/client";
import type { RepoRetrospective, RetrospectiveInsight } from "../../api/types";

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  critical: { color: "text-status-failed", bg: "bg-status-failed/10", label: "Critical" },
  warning: { color: "text-amber-400", bg: "bg-amber-400/10", label: "Warning" },
  info: { color: "text-text-muted", bg: "bg-bg-elevated", label: "Info" },
};

const CATEGORY_LABELS: Record<string, string> = {
  efficiency: "Efficiency",
  quality: "Quality",
  cost: "Cost",
  failure: "Failure",
};

function InsightCard({ insight }: { insight: RetrospectiveInsight }) {
  const sev = SEVERITY_CONFIG[insight.severity] || SEVERITY_CONFIG.info;

  return (
    <div
      className={`${sev.bg} border border-border-subtle rounded-lg p-4`}
      data-testid="insight-card"
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <h4 className={`text-sm font-medium ${sev.color}`}>{insight.title}</h4>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-surface text-text-dim border border-border-subtle">
            {CATEGORY_LABELS[insight.category] || insight.category}
          </span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${sev.bg} ${sev.color} font-medium`}>
            {sev.label}
          </span>
        </div>
      </div>
      <p className="text-xs text-text-muted leading-relaxed">{insight.detail}</p>
      {insight.suggestion && (
        <p className="text-xs text-text-dim mt-2 italic">
          Suggestion: {insight.suggestion}
        </p>
      )}
    </div>
  );
}

interface RetrospectivePanelProps {
  crId: string;
  onBack: () => void;
}

export default function RetrospectivePanel({ crId, onBack }: RetrospectivePanelProps) {
  const [data, setData] = useState<RepoRetrospective[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRetrospective(crId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load retrospective");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [crId]);

  const allInsights = data?.flatMap((r) => r.insights) || [];

  // Sort: critical first, then warning, then info
  const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };
  const sorted = [...allInsights].sort(
    (a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3),
  );

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={onBack}
            className="text-[11px] text-text-dim hover:text-accent cursor-pointer bg-transparent border-none transition-colors"
            data-testid="back-button"
          >
            &larr; Back
          </button>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
            Retrospective
          </h2>
        </div>

        {loading && (
          <p className="text-xs text-text-dim" data-testid="loading">
            Loading retrospective...
          </p>
        )}

        {error && (
          <div className="bg-status-failed/10 border border-status-failed/20 rounded-lg p-4">
            <p className="text-xs text-status-failed">{error}</p>
          </div>
        )}

        {!loading && !error && sorted.length === 0 && (
          <div className="bg-bg-elevated border border-border-subtle rounded-lg p-6 text-center">
            <p className="text-xs text-text-dim">
              No retrospective data available yet.
            </p>
          </div>
        )}

        {!loading && sorted.length > 0 && (
          <>
            {/* Summary bar */}
            {data && data.length > 0 && (
              <div className="flex items-center gap-4 mb-4 text-xs text-text-dim">
                <span>
                  Status: <strong className="text-text-muted">{data[0].final_status}</strong>
                </span>
                {data[0].duration_seconds > 0 && (
                  <span>
                    Duration:{" "}
                    <strong className="text-text-muted">
                      {data[0].duration_seconds < 60
                        ? `${data[0].duration_seconds.toFixed(0)}s`
                        : `${(data[0].duration_seconds / 60).toFixed(1)}m`}
                    </strong>
                  </span>
                )}
                <span>
                  Cost: <strong className="text-text-muted">${data[0].total_cost_usd.toFixed(4)}</strong>
                </span>
                <span>
                  {sorted.length} insight{sorted.length !== 1 ? "s" : ""}
                </span>
              </div>
            )}

            {/* Insight cards */}
            <div className="flex flex-col gap-3" data-testid="insights-list">
              {sorted.map((insight, i) => (
                <InsightCard key={i} insight={insight} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
