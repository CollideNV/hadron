import { useState, useMemo } from "react";
import { useStageData } from "../../contexts/StageDataContext";
import { buildSessions } from "../agents/buildSessions";
import { useAutoSelectSession } from "../agents/useAutoSelectSession";
import AgentSessionList from "../agents/AgentSessionList";
import RichConversationView from "../agents/RichConversationView";
import StageSummaryCard, { getStageColor } from "./StageSummaryCard";
import type { PipelineEvent, ReviewFindingData } from "../../api/types";

interface StageDetailViewProps {
  stageName: string;
  onBack: () => void;
}

/** Extract distinct review rounds from findings and sessions. */
function getReviewRounds(findings: PipelineEvent[], sessions: { loopIteration: number }[]): number[] {
  const rounds = new Set<number>();
  for (const f of findings) {
    const d = f.data as ReviewFindingData;
    rounds.add(d.review_round ?? 0);
  }
  for (const s of sessions) {
    rounds.add(s.loopIteration);
  }
  return [...rounds].sort((a, b) => a - b);
}

export default function StageDetailView({
  stageName,
  onBack,
}: StageDetailViewProps) {
  const {
    crId,
    pipelineStatus,
    events,
    toolCalls,
    agentOutputs,
    agentNudges,
    testRuns,
    findings,
  } = useStageData();

  const allSessions = useMemo(
    () => buildSessions(events, toolCalls, agentOutputs, agentNudges),
    [events, toolCalls, agentOutputs, agentNudges],
  );

  const isReview = stageName === "review";
  const reviewRounds = useMemo(
    () => (isReview ? getReviewRounds(findings, allSessions) : []),
    [isReview, findings, allSessions],
  );
  const hasMultipleRounds = reviewRounds.length > 1;

  const [selectedRound, setSelectedRound] = useState<number | null>(null);

  // Filter sessions and findings by selected review round
  const sessions = useMemo(() => {
    if (!isReview || selectedRound === null) return allSessions;
    return allSessions.filter((s) => s.loopIteration === selectedRound);
  }, [allSessions, isReview, selectedRound]);

  const filteredFindings = useMemo(() => {
    if (!isReview || selectedRound === null) return findings;
    return findings.filter((f) => {
      const d = f.data as ReviewFindingData;
      return (d.review_round ?? 0) === selectedRound;
    });
  }, [findings, isReview, selectedRound]);

  const { selectedIndex, selectedSession, setSelectedIndex } = useAutoSelectSession(sessions);
  const color = getStageColor(stageName);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left sidebar */}
      <div className="w-80 flex-shrink-0 border-r border-border-subtle flex flex-col overflow-hidden bg-bg-surface">
        {/* Back button + stage name */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border-subtle">
          <button
            onClick={onBack}
            className="text-[11px] text-text-dim hover:text-accent cursor-pointer bg-transparent border-none transition-colors"
          >
            &larr; Back
          </button>
          <h3
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color }}
          >
            {stageName.replace(/_/g, " ")}
          </h3>
        </div>

        {/* Review round tabs */}
        {isReview && hasMultipleRounds && (
          <div className="flex items-center gap-1 px-3 py-2 border-b border-border-subtle">
            <button
              onClick={() => setSelectedRound(null)}
              className={`text-[10px] px-2 py-0.5 rounded border cursor-pointer transition-colors ${
                selectedRound === null
                  ? "bg-accent/15 border-accent/30 text-accent font-medium"
                  : "border-border-subtle text-text-dim hover:text-text-muted bg-transparent"
              }`}
            >
              All
            </button>
            {reviewRounds.map((round) => (
              <button
                key={round}
                onClick={() => setSelectedRound(round === selectedRound ? null : round)}
                className={`text-[10px] px-2 py-0.5 rounded border cursor-pointer transition-colors ${
                  selectedRound === round
                    ? "bg-accent/15 border-accent/30 text-accent font-medium"
                    : "border-border-subtle text-text-dim hover:text-text-muted bg-transparent"
                }`}
              >
                Review {round + 1}
              </button>
            ))}
          </div>
        )}

        {/* Summary card */}
        <StageSummaryCard
          stageName={stageName}
          events={events}
          sessions={sessions}
          testRuns={testRuns}
          findings={filteredFindings}
        />

        {/* Session list */}
        <div className="flex-1 overflow-y-auto">
          {sessions.length === 0 ? (
            <p className="text-xs text-text-dim py-4 text-center">
              No agent sessions
            </p>
          ) : (
            <AgentSessionList
              sessions={sessions}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
            />
          )}
        </div>
      </div>

      {/* Right content: rich conversation */}
      <div className="flex-1 overflow-hidden">
        {selectedSession ? (
          <RichConversationView
            session={selectedSession}
            crId={crId}
            pipelineStatus={pipelineStatus}
            testRuns={testRuns}
            findings={filteredFindings}
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-text-dim">
              {sessions.length === 0
                ? "No agent activity for this stage yet"
                : "Select a session"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
