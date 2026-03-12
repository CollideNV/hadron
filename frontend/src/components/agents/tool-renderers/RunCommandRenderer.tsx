import { useState } from "react";
import type { RichToolCallProps } from "./helpers";
import { getInput, extractExitCode } from "./helpers";

export default function RunCommandRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(true);
  const input = getInput(call);
  const command = String(input.command || input.cmd || "");
  const exitCode = result ? extractExitCode(result.result) : null;

  return (
    <div className="border border-border-subtle rounded-md overflow-hidden text-xs">
      <div className="flex items-center gap-2 px-2.5 py-1.5 bg-[#0d1117]">
        <span className="text-text-dim text-[10px]">$</span>
        <code className="font-mono text-[11px] text-text flex-1 truncate">{command}</code>
        {exitCode !== null && (
          <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${
            exitCode === 0 ? "bg-status-completed/15 text-status-completed" : "bg-status-failed/15 text-status-failed"
          }`}>
            exit {exitCode}
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-text-dim text-[10px] cursor-pointer bg-transparent border-none text-inherit"
        >
          {collapsed ? "expand" : "collapse"}
        </button>
      </div>
      {!collapsed && result && (
        <pre className="px-3 py-2 text-[11px] text-text-muted bg-[#0d1117] overflow-auto max-h-64 m-0 whitespace-pre-wrap leading-relaxed border-t border-border-subtle/30">
          {result.result}
        </pre>
      )}
    </div>
  );
}
