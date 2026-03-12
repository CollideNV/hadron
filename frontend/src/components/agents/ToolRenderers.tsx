import { useState } from "react";
import type { ConversationItem } from "./types";

type ToolCallItem = Extract<ConversationItem, { type: "tool_call" }>;
type ToolResultItem = Extract<ConversationItem, { type: "tool_result" }>;

interface RichToolCallProps {
  call: ToolCallItem;
  result?: ToolResultItem;
}

function getInput(call: ToolCallItem): Record<string, unknown> {
  if (typeof call.input === "object" && call.input !== null) {
    return call.input as Record<string, unknown>;
  }
  return {};
}

/* ── File viewer (read_file) ── */
function ReadFileRenderer({ call, result }: RichToolCallProps) {
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

/* ── File writer (write_file) ── */
function WriteFileRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(false);
  const input = getInput(call);
  const path = String(input.path || input.file_path || "");
  const content = String(input.content || "");

  return (
    <div className="border border-border-subtle rounded-md overflow-hidden text-xs border-l-2 border-l-status-completed/50">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 bg-bg-surface cursor-pointer border-none text-inherit"
      >
        <span className="text-status-completed/70 text-[10px]">&#9998;</span>
        <span className="font-mono text-status-completed text-[11px] font-medium truncate">{path}</span>
        <span className="text-text-dim text-[10px] ml-auto flex-shrink-0">
          {collapsed ? "expand" : "collapse"}
        </span>
      </button>
      {!collapsed && (
        <pre className="px-3 py-2 text-[11px] text-text-muted bg-bg/50 overflow-auto max-h-64 m-0 whitespace-pre-wrap leading-relaxed border-t border-border-subtle">
          {content || result?.result || "(empty)"}
        </pre>
      )}
    </div>
  );
}

/* ── Directory listing ── */
function ListDirectoryRenderer({ call, result }: RichToolCallProps) {
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

/* ── Terminal command ── */
function RunCommandRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(false);
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

/* ── Search results ── */
function SearchFilesRenderer({ call, result }: RichToolCallProps) {
  const [collapsed, setCollapsed] = useState(true);
  const input = getInput(call);
  const pattern = String(input.pattern || input.query || input.regex || "");

  return (
    <div className="border border-border-subtle rounded-md overflow-hidden text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-2 w-full text-left px-2.5 py-1.5 bg-bg-surface cursor-pointer border-none text-inherit"
      >
        <span className="text-text-dim text-[10px]">&#128269;</span>
        <span className="font-mono text-accent/80 text-[11px]">{pattern}</span>
        {result && (
          <span className="text-text-dim text-[10px]">
            {countMatches(result.result)} match{countMatches(result.result) !== 1 ? "es" : ""}
          </span>
        )}
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

/* ── Fallback: key-value pairs ── */
function FallbackRenderer({ call, result }: RichToolCallProps) {
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

/* ── Dispatcher ── */
const TOOL_RENDERERS: Record<string, React.FC<RichToolCallProps>> = {
  read_file: ReadFileRenderer,
  write_file: WriteFileRenderer,
  list_directory: ListDirectoryRenderer,
  run_command: RunCommandRenderer,
  execute_command: RunCommandRenderer,
  bash: RunCommandRenderer,
  search_files: SearchFilesRenderer,
  grep: SearchFilesRenderer,
};

export default function RichToolCall({ call, result }: RichToolCallProps) {
  const Renderer = TOOL_RENDERERS[call.tool] || FallbackRenderer;
  return <Renderer call={call} result={result} />;
}

/* ── Helpers ── */
function addLineNumbers(text: string): string {
  const lines = text.split("\n");
  if (lines.length <= 1) return text;
  const width = String(lines.length).length;
  return lines
    .map((line, i) => `${String(i + 1).padStart(width)} | ${line}`)
    .join("\n");
}

function extractExitCode(result: string): number | null {
  const match = result.match(/exit[_ ]code[:\s]+(\d+)/i);
  if (match) return parseInt(match[1], 10);
  // Check if result ends with a line like "0" or "1"
  const lines = result.trim().split("\n");
  const last = lines[lines.length - 1]?.trim();
  if (last && /^exit \d+$/.test(last)) return parseInt(last.split(" ")[1], 10);
  return null;
}

function countMatches(result: string): number {
  return result.split("\n").filter((l) => l.trim()).length;
}
