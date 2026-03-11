import type { PipelineEvent } from "./api/types";
import type { CRRun } from "./api/types";

export function makeEvent(
  overrides: Partial<PipelineEvent> & { event_type: string },
): PipelineEvent {
  return {
    cr_id: "cr-1",
    stage: "intake",
    data: {},
    timestamp: 1700000000,
    ...overrides,
  };
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
