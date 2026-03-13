import { useMemo } from "react";
import { useStageData } from "../../contexts/StageDataContext";
import { buildSessions } from "../agents/buildSessions";
import { useAutoSelectSession } from "../agents/useAutoSelectSession";
import AgentSessionList from "../agents/AgentSessionList";
import RichConversationView from "../agents/RichConversationView";
import StageSummaryCard, { getStageColor } from "./StageSummaryCard";

interface StageDetailViewProps {
  stageName: string;
  onBack: () => void;
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

  const sessions = useMemo(
    () => buildSessions(events, toolCalls, agentOutputs, agentNudges),
    [events, toolCalls, agentOutputs, agentNudges],
  );
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

        {/* Summary card */}
        <StageSummaryCard
          stageName={stageName}
          events={events}
          sessions={sessions}
          testRuns={testRuns}
          findings={findings}
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
            findings={findings}
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
