import { useState } from "react";
import type { PipelineEvent } from "../../api/types";

interface TestResultsPanelProps {
  testRuns: PipelineEvent[];
}

export default function TestResultsPanel({ testRuns }: TestResultsPanelProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-subtle">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Test Results
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2">
        {testRuns.length === 0 && (
          <p className="text-xs text-text-dim py-4 text-center">
            No test runs yet
          </p>
        )}
        {testRuns.map((run, i) => (
          <TestRunCard key={i} event={run} />
        ))}
      </div>
    </div>
  );
}

function TestRunCard({ event }: { event: PipelineEvent }) {
  const [expanded, setExpanded] = useState(false);
  const d = event.data;
  const passed = d.passed as boolean;
  const iteration = d.iteration as number;
  const output = (d.output_tail as string) || "";

  return (
    <div
      className={`border rounded-lg px-3 py-2.5 animate-fade-in ${
        passed
          ? "border-status-completed/20 bg-status-completed/5"
          : "border-status-failed/20 bg-status-failed/5"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span
            className={`text-xs font-bold ${passed ? "text-status-completed" : "text-status-failed"}`}
          >
            {passed ? "PASS" : "FAIL"}
          </span>
          <span className="text-[11px] text-text-muted">
            Iteration {iteration}
            {d.repo ? ` - ${String(d.repo)}` : ""}
          </span>
        </div>
        {output && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-text-dim hover:text-text-muted cursor-pointer bg-transparent border-none transition-colors"
          >
            {expanded ? "Hide" : "Show"} output
          </button>
        )}
      </div>
      {expanded && output && (
        <pre className="mt-2 text-[10px] text-text-muted bg-bg rounded-md p-2.5 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto border border-border-subtle">
          {output}
        </pre>
      )}
    </div>
  );
}
