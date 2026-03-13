import type { PipelineEvent } from "../../api/types";
import { SEVERITY_STYLES } from "../../utils/constants";

export function InlineTestRun({ event }: { event: PipelineEvent }) {
  if (event.event_type !== "test_run") return null;
  const { passed, iteration, repo } = event.data;
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
        Iteration {iteration}
        {repo ? ` - ${repo}` : ""}
      </span>
    </div>
  );
}

export function InlineFinding({ event }: { event: PipelineEvent }) {
  if (event.event_type !== "review_finding") return null;
  const { severity, message, file, line } = event.data;
  const sev = severity || "info";
  return (
    <div className={`px-3 py-1.5 rounded-md text-xs border ${SEVERITY_STYLES[sev] || SEVERITY_STYLES.info}`}>
      <div className="flex items-center gap-2">
        <span className="font-bold uppercase text-[9px] tracking-wider">{sev}</span>
        {file ? (
          <span className="font-mono text-text-muted text-[10px]">
            {file}{line ? `:${line}` : ""}
          </span>
        ) : null}
      </div>
      <p className="mt-0.5 text-text-muted text-[11px]">
        {message || "No message"}
      </p>
    </div>
  );
}
