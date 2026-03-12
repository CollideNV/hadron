import { useState } from "react";
import type { RichToolCallProps } from "./helpers";
import { getInput, addLineNumbers } from "./helpers";

export default function ReadFileRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(false);
  const input = getInput(call);
  const path = String(input.path || input.file_path || "");

  return (
    <div className="border border-border-subtle rounded-md overflow-hidden text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 bg-bg-surface cursor-pointer border-none text-inherit"
      >
        <span className="text-accent/70 text-[10px]">&#128196;</span>
        <span className="font-mono text-accent text-[11px] font-medium truncate">{path}</span>
        <span className="text-text-dim text-[10px] ml-auto flex-shrink-0">
          {collapsed ? "expand" : "collapse"}
        </span>
      </button>
      {!collapsed && result && (
        <pre className="px-3 py-2 text-[11px] text-text-muted bg-bg/50 overflow-auto max-h-64 m-0 whitespace-pre-wrap leading-relaxed border-t border-border-subtle">
          {addLineNumbers(result.result)}
        </pre>
      )}
    </div>
  );
}
