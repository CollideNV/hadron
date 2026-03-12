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
}

export type ConversationItem =
  | { type: "output"; text: string; round: number; ts: number }
  | { type: "tool_call"; tool: string; input: unknown; round: number; ts: number }
  | { type: "tool_result"; tool: string; result: string; round: number; ts: number }
  | { type: "nudge"; text: string; ts: number };

export function buildSessions(
  events: PipelineEvent[],
  toolCalls: PipelineEvent[],
  agentOutputs: PipelineEvent[],
  agentNudges: PipelineEvent[],
): AgentSession[] {
  const sessions: AgentSession[] = [];
  const sessionMap = new Map<string, AgentSession>();

  const getSession = (role: string, repo: string, stage: string): AgentSession => {
    const key = `${stage}:${role}:${repo}`;
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
      };
      sessionMap.set(key, session);
      sessions.push(session);
    }
    return session;
  };

  const allEvents = [
    ...events.filter(
      (e) =>
        e.event_type === "agent_started" || e.event_type === "agent_completed",
    ),
    ...toolCalls,
    ...agentOutputs,
    ...agentNudges,
  ].sort((a, b) => a.timestamp - b.timestamp);

  for (const e of allEvents) {
    if (e.event_type === "agent_started") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage);
      session.model = e.data.model || undefined;
      session.models = e.data.models || undefined;
      session.allowedTools = e.data.allowed_tools || undefined;
    } else if (e.event_type === "agent_completed") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage);
      session.completed = true;
      session.model = session.model || e.data.model || undefined;
      session.inputTokens = e.data.input_tokens || 0;
      session.outputTokens = e.data.output_tokens || 0;
      session.costUsd = e.data.cost_usd || 0;
      session.roundCount = e.data.round_count || 0;
      session.conversationKey = e.data.conversation_key || undefined;
      session.throttleCount = e.data.throttle_count || 0;
      session.throttleSeconds = e.data.throttle_seconds || 0;
      session.modelBreakdown = e.data.model_breakdown || {};
    } else if (e.event_type === "agent_output") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage);
      session.items.push({
        type: "output",
        text: e.data.text || "",
        round: e.data.round || 0,
        ts: e.timestamp,
      });
    } else if (e.event_type === "agent_tool_call") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage);
      const subtype = e.data.type || "";
      if (subtype === "result") {
        session.items.push({
          type: "tool_result",
          tool: e.data.tool || "",
          result: e.data.result || "",
          round: e.data.round || 0,
          ts: e.timestamp,
        });
      } else {
        session.items.push({
          type: "tool_call",
          tool: e.data.tool || "",
          input: e.data.input || {},
          round: e.data.round || 0,
          ts: e.timestamp,
        });
        if (e.data.result_snippet && !subtype) {
          session.items.push({
            type: "tool_result",
            tool: e.data.tool || "",
            result: e.data.result_snippet || "",
            round: e.data.round || 0,
            ts: e.timestamp + 0.001,
          });
        }
      }
    } else if (e.event_type === "agent_nudge") {
      const session = getSession(e.data.role || "", e.data.repo || "", e.stage);
      session.items.push({
        type: "nudge",
        text: e.data.text || "",
        ts: e.timestamp,
      });
    }
  }

  return sessions;
}
