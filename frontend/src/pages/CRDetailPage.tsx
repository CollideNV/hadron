import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getPipelineStatus } from "../api/client";
import type { CRRunDetail } from "../api/types";
import { useEventStream } from "../hooks/useEventStream";
import CRStatusBadge from "../components/cr/CRStatusBadge";
import CostTracker from "../components/cost/CostTracker";
import InterventionModal from "../components/intervention/InterventionModal";
import ResumeModal from "../components/intervention/ResumeModal";
import StageTimeline from "../components/pipeline/StageTimeline";
import EventLog from "../components/events/EventLog";
import StageDetailView from "../components/stages/StageDetailView";
import LogsPanel from "../components/logs/LogsPanel";

export default function CRDetailPage() {
  const { crId } = useParams<{ crId: string }>();
  const [crRun, setCrRun] = useState<CRRunDetail | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const stream = useEventStream(crId);

  useEffect(() => {
    if (!crId) return;
    getPipelineStatus(crId).then(setCrRun).catch(() => {});
  }, [crId]);

  if (!crId) return null;

  // Re-fetch CR status periodically to catch stale stream state
  // (e.g. worker crashed without emitting a terminal event)
  useEffect(() => {
    if (!crId) return;
    if (stream.status !== "running") return;
    const interval = setInterval(() => {
      getPipelineStatus(crId).then(setCrRun).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [crId, stream.status]);

  // Trust the API status when stream says "running" but DB says terminal
  const apiStatus = crRun?.status;
  const isStreamStale =
    stream.status === "running" &&
    (apiStatus === "paused" || apiStatus === "failed" || apiStatus === "completed");
  const displayStatus =
    stream.status === "connecting"
      ? apiStatus || "pending"
      : isStreamStale
        ? apiStatus!
        : stream.status;
  const title = crRun?.title || "Loading...";

  // Filter events by selected stage
  const filteredEvents = selectedStage
    ? stream.events.filter(
        (e) =>
          e.stage === selectedStage ||
          e.stage.startsWith(selectedStage + ":") ||
          e.event_type === "pipeline_started" ||
          e.event_type === "pipeline_resumed" ||
          e.event_type === "pipeline_completed" ||
          e.event_type === "pipeline_failed",
      )
    : stream.events;

  const filteredToolCalls = selectedStage
    ? stream.toolCalls.filter(
        (e) =>
          e.stage === selectedStage ||
          e.stage.startsWith(selectedStage + ":"),
      )
    : stream.toolCalls;

  const filteredAgentOutputs = selectedStage
    ? stream.agentOutputs.filter(
        (e) =>
          e.stage === selectedStage ||
          e.stage.startsWith(selectedStage + ":"),
      )
    : stream.agentOutputs;

  const filteredAgentNudges = selectedStage
    ? stream.agentNudges.filter(
        (e) =>
          e.stage === selectedStage ||
          e.stage.startsWith(selectedStage + ":"),
      )
    : stream.agentNudges;

  const filteredTestRuns = selectedStage
    ? stream.testRuns.filter((e) => e.stage === selectedStage)
    : stream.testRuns;

  const filteredFindings = selectedStage
    ? stream.reviewFindings.filter((e) => e.stage === selectedStage)
    : stream.reviewFindings;

  const handleSelectStage = (stage: string) => {
    setSelectedStage(stage === selectedStage ? null : stage);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-49px)]">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-bg-surface border-b border-border-subtle">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/"
            className="text-text-dim hover:text-text no-underline text-sm transition-colors"
          >
            &larr;
          </Link>
          <span className="font-mono text-[11px] text-text-dim">{crId}</span>
          <span className="text-sm font-medium text-text truncate">
            {title}
          </span>
          <CRStatusBadge status={displayStatus} />
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowLogs(!showLogs)}
            className={`px-2.5 py-1 text-[11px] font-medium rounded cursor-pointer border transition-colors ${
              showLogs
                ? "bg-accent/15 text-accent border-accent/30"
                : "bg-transparent text-text-dim border-border-subtle hover:text-text hover:border-border-subtle"
            }`}
          >
            Logs
          </button>
          <CostTracker
            costUsd={stream.costUsd || crRun?.cost_usd || 0}
          />
          <ResumeModal crId={crId} status={displayStatus} />
          <InterventionModal crId={crId} />
        </div>
      </div>

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
        <div className="bg-bg-card border-b border-border-subtle px-4 py-1.5 flex items-center gap-2">
          <span className="text-[10px] text-text-dim uppercase tracking-wider">
            Stage
          </span>
          <span className="text-xs text-accent font-medium">
            {selectedStage.replace(/_/g, " ")}
          </span>
          <button
            onClick={() => setSelectedStage(null)}
            className="text-[10px] text-text-dim hover:text-text ml-auto cursor-pointer bg-transparent border-none transition-colors"
          >
            Close
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-hidden">
          {selectedStage ? (
            <StageDetailView
              crId={crId}
              stageName={selectedStage}
              events={filteredEvents}
              toolCalls={filteredToolCalls}
              agentOutputs={filteredAgentOutputs}
              agentNudges={filteredAgentNudges}
              testRuns={filteredTestRuns}
              findings={filteredFindings}
              pipelineStatus={displayStatus}
              onBack={() => setSelectedStage(null)}
            />
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
