export default function EventBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    test_run: "bg-accent/10 text-accent/80",
    review_finding: "bg-status-paused/10 text-status-paused",
    cost_update: "bg-bg-elevated text-text-dim",
    error: "bg-status-failed/15 text-status-failed",
  };
  return (
    <span
      className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-medium whitespace-nowrap ${styles[type] || "bg-bg-elevated text-text-dim"}`}
    >
      {type.replace(/_/g, " ")}
    </span>
  );
}
