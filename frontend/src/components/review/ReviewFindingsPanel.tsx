import type { PipelineEvent } from "../../api/types";

const SEVERITY_STYLES: Record<string, string> = {
  critical:
    "border-severity-critical/25 bg-severity-critical/8 text-severity-critical",
  major: "border-severity-major/25 bg-severity-major/8 text-severity-major",
  minor: "border-severity-minor/25 bg-severity-minor/8 text-severity-minor",
  info: "border-severity-info/25 bg-severity-info/8 text-severity-info",
};

interface ReviewFindingsPanelProps {
  findings: PipelineEvent[];
}

export default function ReviewFindingsPanel({
  findings,
}: ReviewFindingsPanelProps) {
  const grouped: Record<string, PipelineEvent[]> = {};
  for (const f of findings) {
    const sev = (f.data.severity as string) || "info";
    (grouped[sev] ??= []).push(f);
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
            const d = f.data;
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
                  {d.file ? (
                    <span className="font-mono text-text-muted text-[10px]">
                      {String(d.file)}
                      {d.line ? `:${String(d.line)}` : ""}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-text-muted text-[11px]">
                  {(d.message as string) || "No message"}
                </p>
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
