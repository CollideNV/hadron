export interface CRRun {
  cr_id: string;
  title: string;
  status: string;
  source: string;
  external_id: string | null;
  cost_usd: number;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PipelineEvent {
  cr_id: string;
  event_type: string;
  stage: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface RawChangeRequest {
  title: string;
  description: string;
  source?: string;
  repo_url?: string;
  repo_default_branch?: string;
  test_command?: string;
  language?: string;
}

export const EVENT_TYPES = [
  "pipeline_started",
  "pipeline_completed",
  "pipeline_failed",
  "pipeline_paused",
  "stage_entered",
  "stage_completed",
  "agent_started",
  "agent_completed",
  "agent_tool_call",
  "agent_output",
  "agent_nudge",
  "test_run",
  "review_finding",
  "intervention_set",
  "cost_update",
  "error",
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

export const STAGES = [
  "intake",
  "repo_id",
  "worktree_setup",
  "behaviour_translation",
  "behaviour_verification",
  "tdd",
  "review",
  "rebase",
  "delivery",
  "release_gate",
  "release",
  "retrospective",
] as const;

export type Stage = (typeof STAGES)[number];
