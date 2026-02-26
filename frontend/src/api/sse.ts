import type { PipelineEvent, EventType } from "./types";

type EventCallback = (event: PipelineEvent) => void;

/**
 * Connect to the SSE event stream for a CR.
 * Uses addEventListener for each named event type (backend sets SSE `event:` field).
 */
export function connectEventStream(
  crId: string,
  onEvent: EventCallback,
  onError?: (err: Event) => void,
): () => void {
  const url = `/api/events/stream?cr_id=${encodeURIComponent(crId)}`;
  const source = new EventSource(url);

  const EVENT_NAMES: EventType[] = [
    "pipeline_started",
    "pipeline_completed",
    "pipeline_failed",
    "pipeline_paused",
    "stage_entered",
    "stage_completed",
    "agent_started",
    "agent_completed",
    "agent_tool_call",
    "test_run",
    "review_finding",
    "intervention_set",
    "cost_update",
    "error",
  ];

  for (const name of EVENT_NAMES) {
    source.addEventListener(name, (e: MessageEvent) => {
      try {
        const event: PipelineEvent = JSON.parse(e.data);
        onEvent(event);
      } catch {
        // ignore parse errors
      }
    });
  }

  source.onerror = (e) => {
    onError?.(e);
  };

  return () => source.close();
}
