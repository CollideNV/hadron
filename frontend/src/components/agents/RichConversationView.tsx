import { useState, useMemo } from "react";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import type { PipelineEvent } from "../../api/types";
import type { AgentSession, ConversationItem } from "./types";
import { buildTimeline } from "../../utils/buildTimeline";
import { formatModelName, formatTokenPair } from "../../utils/format";
import NudgeInput from "./NudgeInput";
import SessionHeader from "./SessionHeader";
import TokenInfoFooter from "./TokenInfoFooter";
import TimelineEntry, { PHASE_LABELS } from "./TimelineEntry";

interface RichConversationViewProps {
  session: AgentSession;
  crId: string;
  pipelineStatus: string;
  testRuns?: PipelineEvent[];
  findings?: PipelineEvent[];
}

/** Extract distinct phases from conversation items, preserving order. */
function getPhases(items: ConversationItem[]): Array<{ phase: string; model: string }> {
  const seen = new Set<string>();
  const phases: Array<{ phase: string; model: string }> = [];
  for (const item of items) {
    if (item.type === "phase_started" && !seen.has(item.phase)) {
      seen.add(item.phase);
      phases.push({ phase: item.phase, model: item.model });
    }
  }
  return phases;
}

export default function RichConversationView({
  session,
  crId,
  pipelineStatus,
  testRuns = [],
  findings = [],
}: RichConversationViewProps) {
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null);

  const isActive =
    !session.completed &&
    (pipelineStatus === "running" || pipelineStatus === "connecting");

  const tokenInfo = session.inputTokens
    ? `${formatTokenPair(session.inputTokens, session.outputTokens)} tok`
    : "";

  const phases = useMemo(() => getPhases(session.items), [session.items]);

  // Filter items by selected phase (null = show all)
  const filteredItems = useMemo(() => {
    if (!selectedPhase) return session.items;
    return session.items.filter(
      (item) =>
        item.type === "phase_started" ||
        item.type === "prompt" ||
        ("phase" in item && item.phase === selectedPhase),
    );
  }, [session.items, selectedPhase]);

  const timeline = useMemo(
    () => buildTimeline(filteredItems, testRuns, findings),
    [filteredItems, testRuns, findings],
  );

  const { scrollRef, onScroll } = useAutoScroll<HTMLDivElement>([timeline.length]);

  // Find which phase is currently active (last phase_started without a following one)
  const activePhase = useMemo(() => {
    for (let i = session.items.length - 1; i >= 0; i--) {
      if (session.items[i].type === "phase_started") {
        return (session.items[i] as Extract<ConversationItem, { type: "phase_started" }>).phase;
      }
    }
    return null;
  }, [session.items]);

  return (
    <div className="flex flex-col h-full">
      <SessionHeader session={session} isActive={isActive} />

      {/* Phase tabs */}
      {phases.length > 0 && (
        <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border-subtle bg-bg-surface flex-shrink-0">
          <button
            onClick={() => setSelectedPhase(null)}
            className={`text-[10px] px-2 py-0.5 rounded border cursor-pointer transition-colors ${
              selectedPhase === null
                ? "bg-accent/15 border-accent/30 text-accent font-medium"
                : "border-border-subtle text-text-dim hover:text-text-muted bg-transparent"
            }`}
          >
            All
          </button>
          {phases.map(({ phase, model }) => (
            <button
              key={phase}
              onClick={() => setSelectedPhase(phase === selectedPhase ? null : phase)}
              className={`text-[10px] px-2 py-0.5 rounded border cursor-pointer transition-colors flex items-center gap-1.5 ${
                selectedPhase === phase
                  ? "bg-accent/15 border-accent/30 text-accent font-medium"
                  : "border-border-subtle text-text-dim hover:text-text-muted bg-transparent"
              }`}
            >
              <span>{PHASE_LABELS[phase] || phase}</span>
              <span className="font-mono opacity-70">{formatModelName(model)}</span>
              {isActive && activePhase === phase && (
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              )}
            </button>
          ))}
        </div>
      )}

      {/* Conversation timeline */}
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {timeline.length === 0 && isActive && (
          <p className="text-xs text-text-dim py-4 text-center animate-pulse">
            Agent is thinking...
          </p>
        )}
        {timeline.map((entry, idx) => (
          <TimelineEntry key={entry.id} entry={entry} idx={idx} selectedPhase={selectedPhase} />
        ))}
      </div>

      {/* Token info footer with per-model breakdown */}
      {tokenInfo && <TokenInfoFooter session={session} tokenInfo={tokenInfo} />}

      {/* Nudge input for active sessions */}
      {isActive && <NudgeInput crId={crId} role={session.role} />}
    </div>
  );
}
