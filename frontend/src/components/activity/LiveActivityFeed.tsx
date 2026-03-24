import { Link } from "react-router-dom";
import { useGlobalActivity } from "../../hooks/useGlobalActivity";
import { STAGE_LABEL } from "../../utils/stages";

const STATUS_DOT: Record<string, string> = {
  running: "bg-accent animate-pulse-glow",
  paused: "bg-status-paused",
  failed: "bg-status-failed",
  completed: "bg-status-completed",
  pending: "bg-status-pending",
};

export default function LiveActivityFeed() {
  const { activities, connected } = useGlobalActivity();

  if (activities.length === 0) {
    return (
      <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="activity-feed">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] text-text-dim uppercase tracking-wider">Live Activity</h2>
          <ConnectionDot connected={connected} />
        </div>
        <p className="text-text-dim text-sm text-center py-6">
          No active pipelines right now.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-4" data-testid="activity-feed">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[10px] text-text-dim uppercase tracking-wider">Live Activity</h2>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-text-dim">{activities.length} active</span>
          <ConnectionDot connected={connected} />
        </div>
      </div>

      <div className="space-y-1">
        {activities.map((item) => (
          <Link
            key={item.cr_id}
            to={`/cr/${item.cr_id}`}
            data-testid={`activity-${item.cr_id}`}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg no-underline hover:bg-bg-card/50 transition-colors group"
          >
            {/* Status dot */}
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[item.status] || "bg-status-pending"}`} />

            {/* CR info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-text-dim">{item.cr_id}</span>
                <span className="text-sm text-text truncate">{item.title}</span>
              </div>
              {item.last_event && (
                <div className="text-[11px] text-text-dim mt-0.5 truncate">{item.last_event}</div>
              )}
            </div>

            {/* Current stage */}
            <span className="text-[11px] text-text-muted bg-bg-card rounded px-2 py-0.5 flex-shrink-0">
              {STAGE_LABEL[item.stage] || item.stage}
            </span>

            {/* Cost */}
            {item.cost_usd > 0 && (
              <span className="font-mono text-[11px] text-accent flex-shrink-0">
                ${item.cost_usd.toFixed(4)}
              </span>
            )}

            {/* Arrow */}
            <span className="text-text-dim group-hover:text-text transition-colors text-sm flex-shrink-0">
              ›
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <span
      data-testid="activity-connection"
      title={connected ? "Connected" : "Disconnected"}
      className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-accent" : "bg-status-failed"}`}
    />
  );
}
