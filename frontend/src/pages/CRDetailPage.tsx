import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useCRDetail } from "../hooks/useCRDetail";
import { StageDataProvider } from "../contexts/StageDataContext";
import CRDetailHeader from "../components/cr/CRDetailHeader";
import StageTimeline from "../components/pipeline/StageTimeline";
import StageFilterBanner from "../components/pipeline/StageFilterBanner";
import EventLog from "../components/events/EventLog";
import StageDetailView from "../components/stages/StageDetailView";
import LogsPanel from "../components/logs/LogsPanel";

export default function CRDetailPage() {
  const { crId, stage: urlStage } = useParams<{ crId: string; stage?: string }>();
  const navigate = useNavigate();
  const selectedStage = urlStage || null;
  const [showLogs, setShowLogs] = useState(false);
  const { crRun, displayStatus, title, stream, filterByStage } = useCRDetail(crId);

  if (!crId) return null;

  const filtered = filterByStage(selectedStage);

  const handleSelectStage = (stage: string) => {
    if (stage === selectedStage) {
      navigate(`/cr/${crId}`, { replace: true });
    } else {
      navigate(`/cr/${crId}/${stage}`, { replace: true });
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-49px)]">
      <CRDetailHeader
        crId={crId}
        title={title}
        displayStatus={displayStatus}
        costUsd={stream.costUsd || crRun?.cost_usd || 0}
        showLogs={showLogs}
        onToggleLogs={() => setShowLogs(!showLogs)}
      />

      {/* Stage timeline */}
      <div className="bg-bg-surface border-b border-border-subtle">
        <StageTimeline
          currentStage={stream.currentStage}
          completedStages={stream.completedStages}
          status={displayStatus}
          selectedStage={selectedStage}
          onSelectStage={handleSelectStage}
          events={stream.events}
        />
      </div>

      {/* Stage filter indicator (overview mode only) */}
      {selectedStage && (
        <StageFilterBanner
          selectedStage={selectedStage}
          onClear={() => navigate(`/cr/${crId}`, { replace: true })}
        />
      )}

      {/* Main content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-hidden">
          {selectedStage ? (
            <StageDataProvider
              crId={crId}
              pipelineStatus={displayStatus}
              events={filtered.events}
              toolCalls={filtered.toolCalls}
              agentOutputs={filtered.agentOutputs}
              agentNudges={filtered.agentNudges}
              testRuns={filtered.testRuns}
              findings={filtered.findings}
            >
              <StageDetailView
                stageName={selectedStage}
                onBack={() => navigate(`/cr/${crId}`, { replace: true })}
              />
            </StageDataProvider>
          ) : (
            <div className="h-full bg-bg-surface overflow-hidden">
              <EventLog
                events={stream.events}
                currentStage={stream.currentStage}
                status={displayStatus}
                onSelectStage={handleSelectStage}
              />
            </div>
          )}
        </div>

        {/* Logs drawer */}
        {showLogs && (
          <div className="h-64 flex-shrink-0 border-t border-border-subtle bg-bg-surface">
            <LogsPanel crId={crId} pipelineStatus={displayStatus} />
          </div>
        )}
      </div>

      {/* Error banner */}
      {stream.error && (
        <div className="bg-status-failed/10 border-t border-status-failed/20 text-status-failed px-4 py-2 text-sm">
          {stream.error}
        </div>
      )}
    </div>
  );
}
