import type { ModelBreakdownEntry } from "../../api/types";

export type { ModelBreakdownEntry } from "../../api/types";

export interface AgentSession {
  role: string;
  repo: string;
  stage: string;
  completed: boolean;
  model?: string;
  models?: string[];
  allowedTools?: string[];
  /** Ordered conversation items built from events */
  items: ConversationItem[];
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  roundCount: number;
  conversationKey?: string;
  throttleCount: number;
  throttleSeconds: number;
  modelBreakdown: Record<string, ModelBreakdownEntry>;
  /** Review loop iteration (0 = first run, 1+ = after review rejection) */
  loopIteration: number;
}

export type PhaseInfo = { phase: string; model: string };

export type ConversationItem =
  | { type: "output"; text: string; round: number; ts: number; phase?: string }
  | { type: "tool_call"; tool: string; input: unknown; round: number; ts: number; phase?: string }
  | { type: "tool_result"; tool: string; result: string; round: number; ts: number; phase?: string }
  | { type: "nudge"; text: string; ts: number; phase?: string }
  | { type: "phase_started"; phase: string; model: string; ts: number }
  | { type: "prompt"; text: string; ts: number };
