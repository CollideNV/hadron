import { useMemo } from "react";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import type { PipelineEvent } from "../../api/types";
import type { AgentSession } from "./types";
import { buildTimeline } from "../../utils/buildTimeline";
import RichToolCall from "./ToolRenderers";
import NudgeInput from "./NudgeInput";
import MarkdownLite from "./MarkdownLite";
import { InlineTestRun, InlineFinding } from "./InlineEventCards";
import SessionHeader from "./SessionHeader";
import TokenInfoFooter from "./TokenInfoFooter";

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
  const { scrollRef, onScroll } = useAutoScroll<HTMLDivElement>([session, testRuns.length, findings.length]);

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
      <SessionHeader session={session} isActive={isActive} />

      {/* Conversation timeline */}
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
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
      {tokenInfo && <TokenInfoFooter session={session} tokenInfo={tokenInfo} />}

      {/* Nudge input for active sessions */}
      {isActive && <NudgeInput crId={crId} role={session.role} />}
    </div>
  );
}
