import { useRef, useEffect } from "react";
import type { PipelineEvent } from "../../api/types";
import type { AgentSession, ConversationItem } from "./types";
import RichToolCall from "./ToolRenderers";
import NudgeInput from "./NudgeInput";
import { formatModelName } from "../../utils/format";

interface RichConversationViewProps {
  session: AgentSession;
  crId: string;
  pipelineStatus: string;
  testRuns?: PipelineEvent[];
  findings?: PipelineEvent[];
}

/* ── Inline event cards ── */
function InlineTestRun({ event }: { event: PipelineEvent }) {
  const d = event.data;
  const passed = d.passed as boolean;
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs ${
      passed
        ? "bg-status-completed/8 border border-status-completed/20"
        : "bg-status-failed/8 border border-status-failed/20"
    }`}>
      <span className={`font-bold text-[10px] ${passed ? "text-status-completed" : "text-status-failed"}`}>
        {passed ? "PASS" : "FAIL"}
      </span>
      <span className="text-text-muted">
        Iteration {d.iteration as number}
        {d.repo ? ` - ${String(d.repo)}` : ""}
      </span>
    </div>
  );
}

function InlineFinding({ event }: { event: PipelineEvent }) {
  const d = event.data;
  const sev = (d.severity as string) || "info";
  const sevColors: Record<string, string> = {
    critical: "text-severity-critical border-severity-critical/20 bg-severity-critical/8",
    major: "text-severity-major border-severity-major/20 bg-severity-major/8",
    minor: "text-severity-minor border-severity-minor/20 bg-severity-minor/8",
    info: "text-severity-info border-severity-info/20 bg-severity-info/8",
  };
  return (
    <div className={`px-3 py-1.5 rounded-md text-xs border ${sevColors[sev] || sevColors.info}`}>
      <div className="flex items-center gap-2">
        <span className="font-bold uppercase text-[9px] tracking-wider">{sev}</span>
        {d.file ? (
          <span className="font-mono text-text-muted text-[10px]">
            {String(d.file)}{d.line ? `:${String(d.line)}` : ""}
          </span>
        ) : null}
      </div>
      <p className="mt-0.5 text-text-muted text-[11px]">
        {(d.message as string) || "No message"}
      </p>
    </div>
  );
}

/* ── Markdown-lite rendering ── */
function MarkdownLite({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  const lines = text.split("\n");
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let codeKey = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        parts.push(
          <pre key={`code-${codeKey++}`} className="bg-bg-surface rounded px-2 py-1.5 text-[11px] text-text-muted overflow-x-auto my-1 whitespace-pre-wrap">
            {codeLines.join("\n")}
          </pre>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }
    parts.push(
      <span key={i}>
        {renderInline(line)}
        {i < lines.length - 1 && "\n"}
      </span>
    );
  }

  // Unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    parts.push(
      <pre key={`code-${codeKey}`} className="bg-bg-surface rounded px-2 py-1.5 text-[11px] text-text-muted overflow-x-auto my-1 whitespace-pre-wrap">
        {codeLines.join("\n")}
      </pre>
    );
  }

  return <div className="text-xs text-text leading-relaxed whitespace-pre-wrap">{parts}</div>;
}

function renderInline(text: string): React.ReactNode {
  // Handle inline code and bold
  const parts: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let match;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const m = match[0];
    if (m.startsWith("`")) {
      parts.push(
        <code key={key++} className="bg-bg-surface rounded px-1 py-0.5 text-[11px] text-accent font-mono">
          {m.slice(1, -1)}
        </code>
      );
    } else if (m.startsWith("**")) {
      parts.push(<strong key={key++}>{m.slice(2, -2)}</strong>);
    }
    last = match.index + m.length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length === 1 ? parts[0] : parts;
}

/* ── Paired items: group tool_call + tool_result ── */
type TimelineItem =
  | { kind: "output"; item: Extract<ConversationItem, { type: "output" }>; ts: number }
  | { kind: "tool"; call: Extract<ConversationItem, { type: "tool_call" }>; result?: Extract<ConversationItem, { type: "tool_result" }>; ts: number }
  | { kind: "nudge"; item: Extract<ConversationItem, { type: "nudge" }>; ts: number }
  | { kind: "test_run"; event: PipelineEvent; ts: number }
  | { kind: "finding"; event: PipelineEvent; ts: number };

function buildTimeline(
  items: ConversationItem[],
  testRuns: PipelineEvent[],
  findings: PipelineEvent[],
): TimelineItem[] {
  const timeline: TimelineItem[] = [];

  // Pair tool calls with results via sequential scan
  let i = 0;
  while (i < items.length) {
    const item = items[i];
    if (item.type === "output") {
      timeline.push({ kind: "output", item, ts: item.ts });
    } else if (item.type === "tool_call") {
      // Check if next item is the matching tool_result
      const next = items[i + 1];
      if (next && next.type === "tool_result" && next.tool === item.tool) {
        timeline.push({ kind: "tool", call: item, result: next, ts: item.ts });
        i++; // skip the result
      } else {
        timeline.push({ kind: "tool", call: item, ts: item.ts });
      }
    } else if (item.type === "tool_result") {
      // Orphan result — render as a fallback tool entry
      timeline.push({
        kind: "tool",
        call: { type: "tool_call", tool: item.tool, input: {}, round: item.round, ts: item.ts },
        result: item,
        ts: item.ts,
      });
    } else if (item.type === "nudge") {
      timeline.push({ kind: "nudge", item, ts: item.ts });
    }
    i++;
  }

  // Interleave test runs and findings by timestamp
  for (const tr of testRuns) {
    timeline.push({ kind: "test_run", event: tr, ts: tr.timestamp });
  }
  for (const f of findings) {
    timeline.push({ kind: "finding", event: f, ts: f.timestamp });
  }

  // Sort everything by timestamp
  timeline.sort((a, b) => a.ts - b.ts);
  return timeline;
}

/* ── Main component ── */
export default function RichConversationView({
  session,
  crId,
  pipelineStatus,
  testRuns = [],
  findings = [],
}: RichConversationViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session, testRuns.length, findings.length]);

  const isActive =
    !session.completed &&
    (pipelineStatus === "running" || pipelineStatus === "connecting");

  const tokenInfo = session.inputTokens
    ? `${(session.inputTokens / 1000).toFixed(1)}k / ${(session.outputTokens / 1000).toFixed(1)}k tok`
    : "";

  const timeline = buildTimeline(session.items, testRuns, findings);

  return (
    <div className="flex flex-col h-full">
      {/* Session header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle bg-bg-surface flex-shrink-0">
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            isActive
              ? "bg-accent animate-pulse-glow"
              : session.completed
                ? "bg-status-completed"
                : "bg-text-dim"
          }`}
        />
        <span className="text-xs font-medium text-text">
          {session.role.replace(/_/g, " ")}
        </span>
        {(session.models && session.models.length > 1 ? session.models : session.model ? [session.model] : []).map((m) => (
          <span key={m} className="text-[10px] text-text-muted font-mono bg-bg-surface border border-border-subtle rounded px-1 py-0.5">
            {formatModelName(m)}
          </span>
        ))}
        {session.repo && (
          <span className="text-[10px] text-text-dim font-mono">
            ({session.repo})
          </span>
        )}
        {session.roundCount > 0 && (
          <span className="text-[10px] text-text-dim">
            round {session.roundCount}
          </span>
        )}
        {session.throttleCount > 0 && (
          <span className="text-[10px] text-status-error" title={`Throttled ${session.throttleCount} time(s), lost ${session.throttleSeconds.toFixed(0)}s`}>
            {session.throttleSeconds.toFixed(0)}s throttled
          </span>
        )}
        {session.costUsd > 0 && (
          <span className="text-[10px] text-accent ml-auto">
            ${session.costUsd.toFixed(3)}
          </span>
        )}
      </div>

      {/* Conversation timeline */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {timeline.length === 0 && isActive && (
          <p className="text-xs text-text-dim py-4 text-center animate-pulse">
            Agent is thinking...
          </p>
        )}
        {timeline.map((entry, idx) => {
          if (entry.kind === "output") {
            return (
              <div key={`${entry.kind}-${entry.ts}-${idx}`} className="animate-fade-in">
                <div className="flex items-start gap-2">
                  <span className="text-[11px] flex-shrink-0 mt-0.5">&#129302;</span>
                  <MarkdownLite text={entry.item.text} />
                </div>
              </div>
            );
          }
          if (entry.kind === "tool") {
            return (
              <div key={`${entry.kind}-${entry.ts}-${idx}`} className="animate-fade-in">
                <RichToolCall call={entry.call} result={entry.result} />
              </div>
            );
          }
          if (entry.kind === "nudge") {
            return (
              <div key={`${entry.kind}-${entry.ts}-${idx}`} className="animate-fade-in">
                <div className="flex items-start gap-2">
                  <span className="text-[11px] flex-shrink-0 mt-0.5">&#128100;</span>
                  <p className="text-xs text-text leading-relaxed bg-accent/10 rounded px-2 py-1 border border-accent/20">
                    {entry.item.text}
                  </p>
                </div>
              </div>
            );
          }
          if (entry.kind === "test_run") {
            return (
              <div key={`${entry.kind}-${entry.ts}-${idx}`} className="animate-fade-in">
                <InlineTestRun event={entry.event} />
              </div>
            );
          }
          if (entry.kind === "finding") {
            return (
              <div key={`${entry.kind}-${entry.ts}-${idx}`} className="animate-fade-in">
                <InlineFinding event={entry.event} />
              </div>
            );
          }
          return null;
        })}
      </div>

      {/* Token info footer with per-model breakdown */}
      {tokenInfo && (
        <div className="border-t border-border-subtle flex-shrink-0">
          {Object.keys(session.modelBreakdown).length > 0 && (
            <div className="px-3 pt-1.5 pb-0.5 space-y-0.5">
              {Object.entries(session.modelBreakdown).map(([model, stats]) => {
                const shortName = formatModelName(model);
                return (
                  <div key={model} className="flex items-center gap-2 text-[10px]">
                    <span className="font-mono text-text-muted w-20 truncate" title={model}>
                      {shortName}
                    </span>
                    <span className="text-text-dim">
                      {(stats.input_tokens / 1000).toFixed(1)}k/{(stats.output_tokens / 1000).toFixed(1)}k tok
                    </span>
                    <span className="text-accent">
                      ${stats.cost_usd.toFixed(4)}
                    </span>
                    {stats.throttle_count > 0 && (
                      <span className="text-status-error">
                        {stats.throttle_seconds.toFixed(0)}s throttled
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="px-3 py-1 text-[10px] text-text-dim text-right flex items-center justify-end gap-3">
            {session.throttleCount > 0 && (
              <span className="text-status-error">
                total: {session.throttleSeconds.toFixed(0)}s throttled
              </span>
            )}
            <span>{tokenInfo}</span>
          </div>
        </div>
      )}

      {/* Nudge input for active sessions */}
      {isActive && <NudgeInput crId={crId} role={session.role} />}
    </div>
  );
}
