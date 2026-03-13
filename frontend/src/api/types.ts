export interface RepoRun {
  repo_name: string;
  repo_url: string;
  status: string;
  branch_name: string | null;
  pr_url: string | null;
  cost_usd: number;
  error: string | null;
}

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

export interface CRRunDetail extends CRRun {
  repos: RepoRun[];
}

/* ── Per-event-type data shapes ── */

export interface PipelineStartedData {}
export interface PipelineResumedData {}
export interface PipelineCompletedData {}
export interface PipelineFailedData {
  error?: string;
}
export interface PipelinePausedData {}
export interface StageEnteredData {}
export interface StageCompletedData {
  error?: string;
}
export interface AgentStartedData {
  role: string;
  repo: string;
  model?: string;
  explore_model?: string;
  plan_model?: string;
  models?: string[];
  allowed_tools?: string[];
}
export interface AgentCompletedData {
  role: string;
  repo: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  model?: string;
  output?: string;
  tool_calls_count?: number;
  round_count?: number;
  conversation_key?: string;
  throttle_count?: number;
  throttle_seconds?: number;
  model_breakdown?: Record<string, ModelBreakdownEntry>;
}
export interface ModelBreakdownEntry {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  throttle_count: number;
  throttle_seconds: number;
  api_calls: number;
}
export interface AgentToolCallData {
  role: string;
  tool: string;
  repo?: string;
  input?: unknown;
  result?: string;
  result_snippet?: string;
  round?: number;
  type?: "call" | "result";
}
export interface AgentOutputData {
  role: string;
  text: string;
  repo?: string;
  round?: number;
}
export interface AgentNudgeData {
  role: string;
  text: string;
  repo?: string;
}
export interface PhaseStartedData {
  role: string;
  repo?: string;
  [k: string]: unknown;
}
export interface PhaseCompletedData {
  role: string;
  repo?: string;
  [k: string]: unknown;
}
export interface TestRunData {
  passed: boolean;
  iteration?: number;
  repo?: string;
  output_tail?: string;
}
export interface ReviewFindingData {
  severity: string;
  message: string;
  file?: string;
  line?: number;
  review_round?: number;
}
export interface InterventionSetData {}
export interface CostUpdateData {
  total_cost_usd?: number;
  delta_usd?: number;
}
export interface AgentPromptData {
  role: string;
  text: string;
  repo?: string;
}
export interface ErrorData {
  message?: string;
  error?: string;
}

/* ── Event-type → data mapping ── */

export interface PipelineEventMap {
  pipeline_started: PipelineStartedData;
  pipeline_resumed: PipelineResumedData;
  pipeline_completed: PipelineCompletedData;
  pipeline_failed: PipelineFailedData;
  pipeline_paused: PipelinePausedData;
  stage_entered: StageEnteredData;
  stage_completed: StageCompletedData;
  agent_started: AgentStartedData;
  agent_completed: AgentCompletedData;
  agent_tool_call: AgentToolCallData;
  agent_output: AgentOutputData;
  agent_nudge: AgentNudgeData;
  phase_started: PhaseStartedData;
  phase_completed: PhaseCompletedData;
  agent_prompt: AgentPromptData;
  test_run: TestRunData;
  review_finding: ReviewFindingData;
  intervention_set: InterventionSetData;
  cost_update: CostUpdateData;
  error: ErrorData;
}

/* ── Discriminated union PipelineEvent ── */

export type PipelineEvent = {
  [K in EventType]: {
    cr_id: string;
    event_type: K;
    stage: string;
    data: PipelineEventMap[K];
    timestamp: number;
  };
}[EventType];

export interface RawChangeRequest {
  title: string;
  description: string;
  source?: string;
  repo_urls?: string[];
  repo_default_branch?: string;
}

export const EVENT_TYPES = [
  "pipeline_started",
  "pipeline_resumed",
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
  "phase_started",
  "phase_completed",
  "agent_prompt",
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
  "implementation",
  "review",
  "rebase",
  "delivery",
  "release_gate",
  "release",
  "retrospective",
] as const;

export type Stage = (typeof STAGES)[number];
