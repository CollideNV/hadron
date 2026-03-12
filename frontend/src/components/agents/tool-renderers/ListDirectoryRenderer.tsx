import { useState } from "react";
import type { RichToolCallProps } from "./helpers";
import { getInput } from "./helpers";

export default function ListDirectoryRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(true);
  const input = getInput(call);
  const path = String(input.path || input.directory || ".");

  return (
    <div className="border border-border-subtle rounded-md overflow-hidden text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 bg-bg-surface cursor-pointer border-none text-inherit"
      >
        <span className="text-text-dim text-[10px]">&#128193;</span>
        <span className="font-mono text-text-muted text-[11px]">{path}</span>
        <span className="text-text-dim text-[10px] ml-auto flex-shrink-0">
          {collapsed ? "expand" : "collapse"}
        </span>
      </button>
      {!collapsed && result && (
        <pre className="px-3 py-2 text-[11px] text-text-muted bg-bg/50 overflow-auto max-h-48 m-0 whitespace-pre-wrap border-t border-border-subtle">
          {result.result}
        </pre>
      )}
    </div>
  );
}
