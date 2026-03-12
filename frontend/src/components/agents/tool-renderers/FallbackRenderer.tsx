import { useState } from "react";
import type { RichToolCallProps } from "./helpers";
import { getInput } from "./helpers";

export default function FallbackRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(true);
  const input = getInput(call);
  const entries = Object.entries(input);
  const summary = entries
    .slice(0, 3)
    .map(([k, v]) => {
      const s = String(v);
      return `${k}: ${s.length > 50 ? s.slice(0, 50) + "..." : s}`;
    })
    .join(", ");

  return (
    <div className="border border-border-subtle rounded-md bg-bg/50 text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left cursor-pointer bg-transparent border-none px-2.5 py-1.5 text-inherit"
      >
        <span className="text-accent/70">&#128295;</span>
        <span className="font-mono font-medium text-accent text-[11px]">{call.tool}</span>
        <span className="text-text-dim truncate flex-1 text-[10px]">{summary}</span>
        <span className="text-text-dim text-[10px] flex-shrink-0">
          {collapsed ? "expand" : "collapse"}
        </span>
      </button>
      {!collapsed && (
        <div className="px-2.5 pb-2 space-y-1 text-[10px] border-t border-border-subtle pt-1.5">
          {entries.map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <span className="text-text-dim font-medium flex-shrink-0">{k}:</span>
              <span className="text-text-muted break-all">{typeof v === "string" ? v : JSON.stringify(v)}</span>
            </div>
          ))}
          {result && (
            <div className="mt-1">
              <span className="text-text-dim font-semibold">Result:</span>
              <pre className="mt-0.5 text-text-muted whitespace-pre-wrap break-all bg-bg-surface rounded p-1.5 max-h-48 overflow-y-auto">
                {result.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
