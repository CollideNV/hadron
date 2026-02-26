const STATUS_STYLES: Record<string, string> = {
  pending: "bg-status-pending/20 text-text-dim",
  running: "bg-accent/12 text-accent",
  completed: "bg-status-completed/12 text-status-completed",
  failed: "bg-status-failed/12 text-status-failed",
  paused: "bg-status-paused/12 text-status-paused",
};

export default function CRStatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  const isRunning = status === "running";
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium ${style}`}
    >
      {isRunning && (
        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-glow" />
      )}
      {status}
    </span>
  );
}
