import type { PipelineEvent, PipelineEventMap } from "../../api/types";
import { SEVERITY_STYLES } from "../../utils/constants";

type ReviewFindingEvent = PipelineEvent & { event_type: "review_finding"; data: PipelineEventMap["review_finding"] };

interface ReviewFindingsPanelProps {
  findings: PipelineEvent[];
}

export default function ReviewFindingsPanel({
  findings,
}: ReviewFindingsPanelProps) {
  const grouped: Record<string, ReviewFindingEvent[]> = {};
  for (const f of findings) {
    const rf = f as ReviewFindingEvent;
    const sev = rf.data.severity || "info";
    (grouped[sev] ??= []).push(rf);
  }

  const order = ["critical", "major", "minor", "info"];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-subtle">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Review Findings
          {findings.length > 0 && (
            <span className="ml-2 text-text-dim normal-case font-normal">
              ({findings.length})
            </span>
          )}
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2">
        {findings.length === 0 && (
          <p className="text-xs text-text-dim py-4 text-center">
            No review findings yet
          </p>
        )}
        {order.map((sev) =>
          (grouped[sev] || []).map((f, i) => {
            const style = SEVERITY_STYLES[sev] || SEVERITY_STYLES.info;
            return (
              <div
                key={`${sev}-${i}`}
                className={`border rounded-lg px-3 py-2.5 text-xs animate-fade-in ${style}`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-bold uppercase text-[9px] tracking-wider">
                    {sev}
                  </span>
                  {f.data.file ? (
                    <span className="font-mono text-text-muted text-[10px]">
                      {f.data.file}
                      {f.data.line ? `:${f.data.line}` : ""}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-text-muted text-[11px]">
                  {f.data.message || "No message"}
                </p>
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
