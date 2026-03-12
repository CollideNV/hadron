import type { PipelineEvent } from "../../api/types";

export function InlineTestRun({ event }: { event: PipelineEvent }) {
  const d = event.data;
  const passed = d.passed as boolean;
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs ${
      passed
        ? "bg-status-completed/8 border border-status-completed/20"
        : "bg-status-failed/8 border border-status-failed/20"
    }`}>
      <span className={`font-bold text-[10px] ${passed ? "text-status-completed" : "text-status-failed"}`}>
        {passed ? "PASS" : "FAIL"}
      </span>
      <span className="text-text-muted">
        Iteration {d.iteration as number}
        {d.repo ? ` - ${String(d.repo)}` : ""}
      </span>
    </div>
  );
}

export function InlineFinding({ event }: { event: PipelineEvent }) {
  const d = event.data;
  const sev = (d.severity as string) || "info";
  const sevColors: Record<string, string> = {
    critical: "text-severity-critical border-severity-critical/20 bg-severity-critical/8",
    major: "text-severity-major border-severity-major/20 bg-severity-major/8",
    minor: "text-severity-minor border-severity-minor/20 bg-severity-minor/8",
    info: "text-severity-info border-severity-info/20 bg-severity-info/8",
  };
  return (
    <div className={`px-3 py-1.5 rounded-md text-xs border ${sevColors[sev] || sevColors.info}`}>
      <div className="flex items-center gap-2">
        <span className="font-bold uppercase text-[9px] tracking-wider">{sev}</span>
        {d.file ? (
          <span className="font-mono text-text-muted text-[10px]">
            {String(d.file)}{d.line ? `:${String(d.line)}` : ""}
          </span>
        ) : null}
      </div>
      <p className="mt-0.5 text-text-muted text-[11px]">
        {(d.message as string) || "No message"}
      </p>
    </div>
  );
}
