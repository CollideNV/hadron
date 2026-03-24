import { useEffect, useRef, useState, useCallback } from "react";
import type { GlobalCRStatus, PipelineEvent } from "../api/types";

export interface ActivityItem {
  cr_id: string;
  title: string;
  stage: string;
  status: string;
  cost_usd: number;
  last_event?: string;
  updated_at: number;
}

export function useGlobalActivity() {
  const [activities, setActivities] = useState<Map<string, ActivityItem>>(new Map());
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (esRef.current) esRef.current.close();

    const es = new EventSource("/api/events/global-stream");
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    // Handle initial CR status snapshots
    es.addEventListener("cr_status", (e) => {
      const data = JSON.parse(e.data) as GlobalCRStatus;
      setActivities((prev) => {
        const next = new Map(prev);
        next.set(data.cr_id, {
          cr_id: data.cr_id,
          title: data.title,
          stage: data.stage,
          status: data.status,
          cost_usd: 0,
          updated_at: Date.now(),
        });
        return next;
      });
    });

    // Handle pipeline events for stage/cost updates
    const eventTypes = [
      "stage_entered", "agent_started", "agent_completed",
      "agent_tool_call", "cost_update", "pipeline_completed",
      "pipeline_failed", "pipeline_paused",
    ];

    for (const eventType of eventTypes) {
      es.addEventListener(eventType, (e) => {
        const event = JSON.parse(e.data) as PipelineEvent;
        setActivities((prev) => {
          const next = new Map(prev);
          const existing = next.get(event.cr_id);
          if (!existing) return prev;

          const updated = { ...existing, updated_at: Date.now() };

          if (eventType === "stage_entered") {
            updated.stage = event.stage;
            updated.last_event = `Entered ${event.stage}`;
          } else if (eventType === "agent_started") {
            updated.last_event = `Agent started: ${(event.data as { role?: string }).role || "unknown"}`;
          } else if (eventType === "agent_tool_call") {
            updated.last_event = `Tool: ${(event.data as { tool?: string }).tool || "unknown"}`;
          } else if (eventType === "cost_update") {
            const costData = event.data as { total_cost_usd?: number };
            if (costData.total_cost_usd != null) updated.cost_usd = costData.total_cost_usd;
          } else if (eventType === "pipeline_completed") {
            updated.status = "completed";
          } else if (eventType === "pipeline_failed") {
            updated.status = "failed";
          } else if (eventType === "pipeline_paused") {
            updated.status = "paused";
          }

          next.set(event.cr_id, updated);
          return next;
        });
      });
    }

    return es;
  }, []);

  useEffect(() => {
    const es = connect();
    return () => es.close();
  }, [connect]);

  return {
    activities: Array.from(activities.values()).sort((a, b) => b.updated_at - a.updated_at),
    connected,
  };
}
