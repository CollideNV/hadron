import type { PipelineEvent, ModelBreakdownEntry } from "../../api/types";

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

export function buildSessions(
  events: PipelineEvent[],
  toolCalls: PipelineEvent[],
  agentOutputs: PipelineEvent[],
  agentNudges: PipelineEvent[],
): AgentSession[] {
  const sessions: AgentSession[] = [];
  const sessionMap = new Map<string, AgentSession>();

  const getSession = (role: string, repo: string, stage: string, loopIteration: number = 0): AgentSession => {
    const key = `${stage}:${role}:${repo}:${loopIteration}`;
    let session = sessionMap.get(key);
    if (!session) {
      session = {
        role,
        repo,
        stage,
        completed: false,
        items: [],
        inputTokens: 0,
        outputTokens: 0,
        costUsd: 0,
        roundCount: 0,
        throttleCount: 0,
        throttleSeconds: 0,
        modelBreakdown: {},
        loopIteration,
      };
      sessionMap.set(key, session);
      sessions.push(session);
    }
    return session;
  };

  // Track current phase and loop iteration per base key (stage:role:repo)
  const currentPhase = new Map<string, string>();
  const currentLoop = new Map<string, number>();

  const allEvents = [
    ...events.filter(
      (e) =>
        e.event_type === "agent_started" || e.event_type === "agent_completed" ||
        e.event_type === "phase_started" || e.event_type === "phase_completed" ||
        e.event_type === "agent_prompt",
    ),
    ...toolCalls,
    ...agentOutputs,
    ...agentNudges,
  ].sort((a, b) => a.timestamp - b.timestamp);

  for (const e of allEvents) {
    const baseKey = `${e.stage}:${e.data.role || ""}:${e.data.repo || ""}`;
    // agent_started/agent_completed carry loop_iteration; other events inherit it
    const loop = e.data.loop_iteration ?? currentLoop.get(baseKey) ?? 0;

    if (e.event_type === "agent_started") {
      currentLoop.set(baseKey, loop);
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      session.model = e.data.model || undefined;
      session.models = e.data.models || undefined;
      session.allowedTools = e.data.allowed_tools || undefined;
      // Reset live breakdown on each agent start (internal iterations)
      session.completed = false;
    } else if (e.event_type === "agent_completed") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      session.completed = true;
      session.model = session.model || e.data.model || undefined;
      session.conversationKey = e.data.conversation_key || undefined;
      // Accumulate costs across internal iterations (e.g. code_writer retries)
      session.inputTokens += e.data.input_tokens || 0;
      session.outputTokens += e.data.output_tokens || 0;
      session.costUsd += e.data.cost_usd || 0;
      session.roundCount += e.data.round_count || 0;
      session.throttleCount += e.data.throttle_count || 0;
      session.throttleSeconds += e.data.throttle_seconds || 0;
      // Merge model breakdown from this agent run
      for (const [model, stats] of Object.entries(e.data.model_breakdown || {})) {
        const existing = session.modelBreakdown[model] || {
          input_tokens: 0, output_tokens: 0, cost_usd: 0,
          throttle_count: 0, throttle_seconds: 0, api_calls: 0,
        };
        session.modelBreakdown[model] = {
          input_tokens: existing.input_tokens + (stats.input_tokens || 0),
          output_tokens: existing.output_tokens + (stats.output_tokens || 0),
          cost_usd: existing.cost_usd + (stats.cost_usd || 0),
          throttle_count: existing.throttle_count + (stats.throttle_count || 0),
          throttle_seconds: existing.throttle_seconds + (stats.throttle_seconds || 0),
          api_calls: existing.api_calls + (stats.api_calls || 0),
        };
      }
    } else if (e.event_type === "agent_prompt") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      // Only add one prompt per session (SSE reconnects may replay events)
      if (!session.items.some((i) => i.type === "prompt")) {
        session.items.push({
          type: "prompt",
          text: e.data.text || "",
          ts: e.timestamp,
        });
      }
    } else if (e.event_type === "phase_started") {
      const phase = e.data.phase || "";
      currentPhase.set(baseKey, phase);
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      session.items.push({
        type: "phase_started",
        phase,
        model: e.data.model || "",
        ts: e.timestamp,
      });
    } else if (e.event_type === "phase_completed") {
      currentPhase.delete(baseKey);
      // Phase stats are only used for live display while agent is running.
      // agent_completed is the authoritative source for final costs.
      // Skip accumulation — agent_completed handles totals correctly.
    } else if (e.event_type === "agent_output") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      session.items.push({
        type: "output",
        text: e.data.text || "",
        round: e.data.round || 0,
        ts: e.timestamp,
        phase: currentPhase.get(baseKey),
      });
    } else if (e.event_type === "agent_tool_call") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      const subtype = e.data.type || "";
      const phase = currentPhase.get(baseKey);
      if (subtype === "result") {
        session.items.push({
          type: "tool_result",
          tool: e.data.tool || "",
          result: e.data.result || "",
          round: e.data.round || 0,
          ts: e.timestamp,
          phase,
        });
      } else {
        session.items.push({
          type: "tool_call",
          tool: e.data.tool || "",
          input: e.data.input || {},
          round: e.data.round || 0,
          ts: e.timestamp,
          phase,
        });
        if (e.data.result_snippet && !subtype) {
          session.items.push({
            type: "tool_result",
            tool: e.data.tool || "",
            result: e.data.result_snippet || "",
            round: e.data.round || 0,
            ts: e.timestamp + 0.001,
            phase,
          });
        }
      }
    } else if (e.event_type === "agent_nudge") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage, loop);
      session.items.push({
        type: "nudge",
        text: e.data.text || "",
        ts: e.timestamp,
        phase: currentPhase.get(baseKey),
      });
    }
  }

  return sessions;
}
