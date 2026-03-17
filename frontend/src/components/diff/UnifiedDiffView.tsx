import { useState } from "react";
import type { StageDiffData } from "../../api/types";

interface DiffFile {
  header: string;
  hunks: string[];
}

function parseDiff(raw: string): DiffFile[] {
  const files: DiffFile[] = [];
  let current: DiffFile | null = null;

  for (const line of raw.split("\n")) {
    if (line.startsWith("diff --git ")) {
      if (current) files.push(current);
      // Extract b/path from "diff --git a/foo b/foo"
      const match = line.match(/b\/(.+)$/);
      current = { header: match?.[1] ?? line, hunks: [] };
    } else if (current) {
      current.hunks.push(line);
    }
  }
  if (current) files.push(current);
  return files;
}

function DiffLine({ line }: { line: string }) {
  if (line.startsWith("@@")) {
    return (
      <div className="text-text-dim text-[11px] bg-accent/5 px-3 py-0.5">
        {line}
      </div>
    );
  }
  if (line.startsWith("+")) {
    return (
      <div className="bg-green-500/10 px-3">
        <span className="text-green-400 select-none mr-2">+</span>
        {line.slice(1)}
      </div>
    );
  }
  if (line.startsWith("-")) {
    return (
      <div className="bg-red-500/10 px-3">
        <span className="text-red-400 select-none mr-2">-</span>
        {line.slice(1)}
      </div>
    );
  }
  return <div className="px-3">{line || "\u00A0"}</div>;
}

interface Props {
  data: StageDiffData;
}

export default function UnifiedDiffView({ data }: Props) {
  const files = parseDiff(data.diff);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const stats = data.stats;

  return (
    <div className="text-xs font-mono">
      {/* Stats bar */}
      {stats && (
        <div className="flex items-center gap-3 px-3 py-2 border-b border-border-subtle text-text-muted text-[11px]">
          <span>{stats.files_changed} file{stats.files_changed !== 1 ? "s" : ""} changed</span>
          <span className="text-green-400">+{stats.insertions}</span>
          <span className="text-red-400">-{stats.deletions}</span>
        </div>
      )}

      {/* Truncation warning */}
      {data.diff_truncated && (
        <div className="px-3 py-1.5 bg-yellow-500/10 text-yellow-400 text-[11px] border-b border-border-subtle">
          Diff truncated (too large to display in full)
        </div>
      )}

      {/* File sections */}
      {files.length === 0 && !data.diff_truncated && (
        <p className="text-text-dim text-[11px] px-3 py-4 text-center">No diff available</p>
      )}
      {files.map((file, i) => (
        <div key={i} className="border-b border-border-subtle last:border-b-0">
          <button
            onClick={() => toggle(i)}
            className="w-full text-left px-3 py-1.5 bg-bg-surface hover:bg-bg text-accent text-[11px] font-semibold cursor-pointer border-none flex items-center gap-1.5 transition-colors"
          >
            <span className="text-text-dim text-[10px]">{collapsed.has(i) ? "\u25B6" : "\u25BC"}</span>
            {file.header}
          </button>
          {!collapsed.has(i) && (
            <div className="overflow-x-auto">
              {file.hunks.map((line, j) => (
                <DiffLine key={j} line={line} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
