import { useEffect, useState, useMemo, useCallback } from "react";
import { getPipelineStatus } from "../api/client";
import type { CRRunDetail, PipelineEvent } from "../api/types";
import { useEventStream, type EventStreamState } from "./useEventStream";

export interface CRDetailState {
  crRun: CRRunDetail | null;
  displayStatus: string;
  title: string;
  stream: EventStreamState;
  filterByStage: (stage: string | null) => FilteredStageData;
}

export interface FilteredStageData {
  events: PipelineEvent[];
  toolCalls: PipelineEvent[];
  agentOutputs: PipelineEvent[];
  agentNudges: PipelineEvent[];
  testRuns: PipelineEvent[];
  findings: PipelineEvent[];
}

function filterEvents(events: PipelineEvent[], stage: string | null): PipelineEvent[] {
  if (!stage) return events;
  return events.filter(
    (e) =>
      e.stage === stage ||
      e.stage.startsWith(stage + ":") ||
      e.event_type === "pipeline_started" ||
      e.event_type === "pipeline_resumed" ||
      e.event_type === "pipeline_completed" ||
      e.event_type === "pipeline_failed",
  );
}

function filterByStagePrefix(events: PipelineEvent[], stage: string | null): PipelineEvent[] {
  if (!stage) return events;
  return events.filter(
    (e) => e.stage === stage || e.stage.startsWith(stage + ":"),
  );
}

function filterByStageExact(events: PipelineEvent[], stage: string | null): PipelineEvent[] {
  if (!stage) return events;
  return events.filter((e) => e.stage === stage);
}

export function useCRDetail(crId: string | undefined): CRDetailState {
  const [crRun, setCrRun] = useState<CRRunDetail | null>(null);
  const stream = useEventStream(crId);

  useEffect(() => {
    if (!crId) return;
    getPipelineStatus(crId).then(setCrRun).catch(() => {});
  }, [crId]);

  // Re-fetch CR status periodically to catch stale stream state
  useEffect(() => {
    if (!crId) return;
    if (stream.status !== "running") return;
    const interval = setInterval(() => {
      getPipelineStatus(crId).then(setCrRun).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [crId, stream.status]);

  // Trust the API status when stream says "running" but DB says terminal
  const displayStatus = useMemo(() => {
    const apiStatus = crRun?.status;
    const isStreamStale =
      stream.status === "running" &&
      (apiStatus === "paused" || apiStatus === "failed" || apiStatus === "completed");
    if (stream.status === "connecting") return apiStatus || "pending";
    if (isStreamStale) return apiStatus!;
    return stream.status;
  }, [stream.status, crRun?.status]);

  const title = crRun?.title || "Loading...";

  const filterByStage = useCallback(
    (stage: string | null): FilteredStageData => ({
      events: filterEvents(stream.events, stage),
      toolCalls: filterByStagePrefix(stream.toolCalls, stage),
      agentOutputs: filterByStagePrefix(stream.agentOutputs, stage),
      agentNudges: filterByStagePrefix(stream.agentNudges, stage),
      testRuns: filterByStageExact(stream.testRuns, stage),
      findings: filterByStageExact(stream.reviewFindings, stage),
    }),
    [stream.events, stream.toolCalls, stream.agentOutputs, stream.agentNudges, stream.testRuns, stream.reviewFindings],
  );

  return { crRun, displayStatus, title, stream, filterByStage };
}
