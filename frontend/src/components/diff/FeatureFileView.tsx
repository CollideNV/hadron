import { useState } from "react";
import type { StageDiffFile } from "../../api/types";

const KEYWORD_RE = /^(Feature|Scenario|Scenario Outline|Background|Examples|Rule):/;
const STEP_RE = /^\s*(Given|When|Then|And|But)\b/;

function highlightLine(line: string): React.ReactNode {
  if (line.trimStart().startsWith("#")) {
    return <span className="text-text-dim">{line}</span>;
  }
  if (KEYWORD_RE.test(line.trimStart())) {
    return <span className="text-accent font-semibold">{line}</span>;
  }
  if (STEP_RE.test(line)) {
    const match = line.match(STEP_RE)!;
    const idx = line.indexOf(match[1]);
    return (
      <>
        {line.slice(0, idx)}
        <span className="text-accent">{match[1]}</span>
        {line.slice(idx + match[1].length)}
      </>
    );
  }
  if (line.trimStart().startsWith("|")) {
    return <span className="text-text-muted">{line}</span>;
  }
  return line;
}

interface Props {
  files: StageDiffFile[];
  truncated?: boolean;
}

export default function FeatureFileView({ files, truncated }: Props) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  if (files.length === 0) {
    return <p className="text-text-dim text-[11px] px-3 py-4 text-center">No feature files</p>;
  }

  return (
    <div className="text-xs font-mono">
      {truncated && (
        <div className="px-3 py-1.5 bg-yellow-500/10 text-yellow-400 text-[11px] border-b border-border-subtle">
          Feature file content truncated (too large to display in full)
        </div>
      )}
      {files.map((file, i) => {
        const lines = file.content.split("\n");
        return (
          <div key={i} className="border-b border-border-subtle last:border-b-0">
            <button
              onClick={() => toggle(i)}
              className="w-full text-left px-3 py-1.5 bg-bg-surface hover:bg-bg text-accent text-[11px] font-semibold cursor-pointer border-none flex items-center gap-1.5 transition-colors"
            >
              <span className="text-text-dim text-[10px]">{collapsed.has(i) ? "\u25B6" : "\u25BC"}</span>
              {file.path}
            </button>
            {!collapsed.has(i) && (
              <div className="overflow-x-auto">
                {lines.map((line, j) => (
                  <div key={j} className="flex">
                    <span className="w-8 text-right pr-2 text-text-dim select-none flex-shrink-0">
                      {j + 1}
                    </span>
                    <span className="flex-1 px-1">{highlightLine(line)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
