import { useEffect, useRef, useCallback, useState } from "react";
import { connectEventStream } from "../api/sse";
import type { PipelineEvent } from "../api/types";
import { reduceEvent, INITIAL_STATE } from "./useEventReducer";
export type { EventStreamState } from "./useEventReducer";

export function useEventStream(crId: string | undefined) {
  const [state, setState] = useState(INITIAL_STATE);
  const closeRef = useRef<(() => void) | null>(null);
  const seenRef = useRef<Set<string>>(new Set());

  const handleEvent = useCallback((event: PipelineEvent) => {
    // Deduplicate events by composite key
    const dedupeKey = `${event.event_type}:${event.stage}:${event.timestamp}`;
    if (seenRef.current.has(dedupeKey)) return;
    seenRef.current.add(dedupeKey);

    setState((prev) => reduceEvent(prev, event));
  }, []);

  useEffect(() => {
    if (!crId) return;

    setState(INITIAL_STATE);
    seenRef.current = new Set();

    const close = connectEventStream(crId, handleEvent, () => {
      // On SSE error, if we haven't received a terminal event, mark as potentially done
      // (the server closes the connection on completion)
    });
    closeRef.current = close;

    return () => {
      close();
      closeRef.current = null;
    };
  }, [crId, handleEvent]);

  return state;
}
