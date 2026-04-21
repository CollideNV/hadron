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
import RetrospectivePanel from "../components/retrospective/RetrospectivePanel";

function pauseReasonToLabel(reason: string | null): string {
  switch (reason) {
    case "budget_exceeded": return "Cost budget exceeded";
    case "circuit_breaker": return "Maximum retry loops reached";
    case "rebase_conflict": return "Merge conflicts during rebase";
    case "waiting_for_ci": return "Waiting for CI results";
    case "error": return "Pipeline error";
    default: return reason || "Unknown reason";
  }
}

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
        events={stream.events}
        showLogs={showLogs}
        onToggleLogs={() => setShowLogs(!showLogs)}
      />

      {/* Stage timeline */}
      <div className="bg-bg-surface border-b border-border-subtle">
        <StageTimeline
          currentStage={stream.currentStage}
          completedStages={stream.completedStages}
          status={displayStatus}
          errorStage={stream.errorStage}
          selectedStage={selectedStage}
          onSelectStage={handleSelectStage}
          events={stream.events}
        />
      </div>

      {/* Pause reason banner */}
      {displayStatus === "paused" && (stream.error || stream.pauseReason) && (
        <div className="bg-amber-950/30 border-b border-amber-800/50 px-4 py-3">
          <div className="flex items-center gap-2 text-amber-300 text-sm font-medium">
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" /></svg>
            Pipeline Paused{stream.errorStage ? ` at ${stream.errorStage.replace(/_/g, " ")}` : ""}
          </div>
          <p className="text-amber-200/80 text-sm mt-1">
            {stream.error || pauseReasonToLabel(stream.pauseReason)}
          </p>
        </div>
      )}

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
            selectedStage === "retrospective" ? (
              <RetrospectivePanel
                crId={crId}
                onBack={() => navigate(`/cr/${crId}`, { replace: true })}
              />
            ) : (
            <StageDataProvider
              crId={crId}
              pipelineStatus={displayStatus}
              events={filtered.events}
              toolCalls={filtered.toolCalls}
              agentOutputs={filtered.agentOutputs}
              agentNudges={filtered.agentNudges}
              testRuns={filtered.testRuns}
              findings={filtered.findings}
              stageDiffs={filtered.stageDiffs}
            >
              <StageDetailView
                stageName={selectedStage}
                onBack={() => navigate(`/cr/${crId}`, { replace: true })}
              />
            </StageDataProvider>
            )
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
