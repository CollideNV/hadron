import { useMemo } from "react";
import type { PipelineEvent } from "../../api/types";
import { buildSessions } from "./buildSessions";
import { useAutoSelectSession } from "./useAutoSelectSession";
import AgentSessionList from "./AgentSessionList";
import RichConversationView from "./RichConversationView";

interface AgentActivityPanelProps {
  crId: string;
  events: PipelineEvent[];
  toolCalls: PipelineEvent[];
  agentOutputs: PipelineEvent[];
  agentNudges: PipelineEvent[];
  pipelineStatus: string;
}

export default function AgentActivityPanel({
  crId,
  events,
  toolCalls,
  agentOutputs,
  agentNudges,
  pipelineStatus,
}: AgentActivityPanelProps) {
  const sessions = useMemo(
    () => buildSessions(events, toolCalls, agentOutputs, agentNudges),
    [events, toolCalls, agentOutputs, agentNudges],
  );
  const { selectedIndex, selectedSession, setSelectedIndex } = useAutoSelectSession(sessions);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-subtle flex-shrink-0">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Agent Activity
        </h3>
      </div>
      {sessions.length === 0 ? (
        <p className="text-xs text-text-dim py-4 text-center flex-1">
          No agent activity yet
        </p>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          {/* Session sidebar */}
          <div className="w-36 flex-shrink-0">
            <AgentSessionList
              sessions={sessions}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
            />
          </div>
          {/* Conversation view */}
          <div className="flex-1 overflow-hidden">
            {selectedSession ? (
              <RichConversationView
                session={selectedSession}
                crId={crId}
                pipelineStatus={pipelineStatus}
              />
            ) : (
              <p className="text-xs text-text-dim py-4 text-center">
                Select a session
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
