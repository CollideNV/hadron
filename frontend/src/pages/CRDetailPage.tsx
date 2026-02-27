import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getPipelineStatus } from "../api/client";
import type { CRRun } from "../api/types";
import { useEventStream } from "../hooks/useEventStream";
import CRStatusBadge from "../components/cr/CRStatusBadge";
import CostTracker from "../components/cost/CostTracker";
import InterventionModal from "../components/intervention/InterventionModal";
import ResumeModal from "../components/intervention/ResumeModal";
import StageTimeline from "../components/pipeline/StageTimeline";
import EventLog from "../components/events/EventLog";
import StageDetailLog from "../components/events/StageDetailLog";
import AgentActivityPanel from "../components/agents/AgentActivityPanel";
import TestResultsPanel from "../components/tests/TestResultsPanel";
import ReviewFindingsPanel from "../components/review/ReviewFindingsPanel";
import LogsPanel from "../components/logs/LogsPanel";

type BottomTab = "tests" | "findings" | "logs";

export default function CRDetailPage() {
  const { crId } = useParams<{ crId: string }>();
  const [crRun, setCrRun] = useState<CRRun | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<BottomTab>("tests");
  const stream = useEventStream(crId);

  useEffect(() => {
    if (!crId) return;
    getPipelineStatus(crId).then(setCrRun).catch(() => {});
  }, [crId]);

  if (!crId) return null;

  const displayStatus =
    stream.status === "connecting" ? crRun?.status || "pending" : stream.status;
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

  const tabClass = (tab: BottomTab) =>
    `px-3 py-1.5 text-[11px] font-medium cursor-pointer bg-transparent border-none transition-colors ${
      bottomTab === tab
        ? "text-accent border-b-2 border-accent"
        : "text-text-dim hover:text-text"
    }`;

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

      {/* Stage filter indicator */}
      {selectedStage && (
        <div className="bg-bg-card border-b border-border-subtle px-4 py-1.5 flex items-center gap-2">
          <span className="text-[10px] text-text-dim uppercase tracking-wider">
            Filtered to
          </span>
          <span className="text-xs text-accent font-medium">
            {selectedStage.replace(/_/g, " ")}
          </span>
          <button
            onClick={() => setSelectedStage(null)}
            className="text-[10px] text-text-dim hover:text-text ml-auto cursor-pointer bg-transparent border-none transition-colors"
          >
            Clear filter
          </button>
        </div>
      )}

      {/* Main content grid */}
      <div className="flex-1 grid grid-cols-2 grid-rows-2 gap-px bg-border-subtle overflow-hidden">
        <div className="bg-bg-surface overflow-hidden">
          {selectedStage ? (
            <StageDetailLog
              events={filteredEvents}
              stageName={selectedStage}
              onBack={() => setSelectedStage(null)}
            />
          ) : (
            <EventLog
              events={stream.events}
              currentStage={stream.currentStage}
              status={displayStatus}
              onSelectStage={handleSelectStage}
            />
          )}
        </div>
        <div className="bg-bg-surface overflow-hidden">
          <AgentActivityPanel
            crId={crId}
            events={filteredEvents}
            toolCalls={filteredToolCalls}
            agentOutputs={filteredAgentOutputs}
            agentNudges={filteredAgentNudges}
            pipelineStatus={displayStatus}
          />
        </div>
        <div className="bg-bg-surface overflow-hidden">
          <TestResultsPanel testRuns={filteredTestRuns} />
        </div>
        <div className="bg-bg-surface overflow-hidden flex flex-col">
          {/* Bottom-right panel with tabs */}
          <div className="flex border-b border-border-subtle flex-shrink-0">
            <button
              onClick={() => setBottomTab("findings")}
              className={tabClass("findings")}
            >
              Findings
            </button>
            <button
              onClick={() => setBottomTab("logs")}
              className={tabClass("logs")}
            >
              Logs
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {bottomTab === "findings" && (
              <ReviewFindingsPanel findings={filteredFindings} />
            )}
            {bottomTab === "logs" && (
              <LogsPanel crId={crId} pipelineStatus={displayStatus} />
            )}
          </div>
        </div>
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
