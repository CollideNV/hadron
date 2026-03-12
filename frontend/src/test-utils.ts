import type { PipelineEvent, EventType } from "./api/types";
import type { CRRun } from "./api/types";

/**
 * Create a PipelineEvent for testing. The event_type determines
 * which data shape is expected. Use `as PipelineEvent` at the
 * boundary since tests often provide partial data.
 */
export function makeEvent(
  overrides: Partial<PipelineEvent> & { event_type: EventType },
): PipelineEvent {
  return {
    cr_id: "cr-1",
    stage: "intake",
    data: {},
    timestamp: 1700000000,
    ...overrides,
  } as PipelineEvent;
}

export function makeCRRun(overrides: Partial<CRRun> = {}): CRRun {
  return {
    cr_id: "cr-1",
    title: "Test CR",
    status: "running",
    source: "api",
    external_id: null,
    cost_usd: 0.1,
    error: null,
    created_at: new Date().toISOString(),
    updated_at: null,
    ...overrides,
  };
}
