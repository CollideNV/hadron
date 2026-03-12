import { useRef, useEffect, useMemo } from "react";
import type { PipelineEvent } from "../../api/types";
import type { AgentSession } from "./types";
import { buildTimeline } from "../../utils/buildTimeline";
import RichToolCall from "./ToolRenderers";
import NudgeInput from "./NudgeInput";
import MarkdownLite from "./MarkdownLite";
import { InlineTestRun, InlineFinding } from "./InlineEventCards";
import { formatModelName } from "../../utils/format";

interface RichConversationViewProps {
  session: AgentSession;
  crId: string;
  pipelineStatus: string;
  testRuns?: PipelineEvent[];
  findings?: PipelineEvent[];
}

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

  const timeline = useMemo(
    () => buildTimeline(session.items, testRuns, findings),
    [session.items, testRuns, findings],
  );

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
