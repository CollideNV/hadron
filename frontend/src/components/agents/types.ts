import type { PipelineEvent } from "../../api/types";

export interface ModelBreakdownEntry {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  throttle_count: number;
  throttle_seconds: number;
}

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
    const role = (e.data.role as string) || "";
    const repo = (e.data.repo as string) || "";

    if (e.event_type === "agent_started") {
      const session = getSession(role, repo, e.stage);
      session.model = (e.data.model as string) || undefined;
      session.models = (e.data.models as string[]) || undefined;
      session.allowedTools = (e.data.allowed_tools as string[]) || undefined;
    } else if (e.event_type === "agent_completed") {
      const session = getSession(role, repo, e.stage);
      session.completed = true;
      session.model = session.model || (e.data.model as string) || undefined;
      session.inputTokens = (e.data.input_tokens as number) || 0;
      session.outputTokens = (e.data.output_tokens as number) || 0;
      session.costUsd = (e.data.cost_usd as number) || 0;
      session.roundCount = (e.data.round_count as number) || 0;
      session.conversationKey = (e.data.conversation_key as string) || undefined;
      session.throttleCount = (e.data.throttle_count as number) || 0;
      session.throttleSeconds = (e.data.throttle_seconds as number) || 0;
      session.modelBreakdown = (e.data.model_breakdown as Record<string, ModelBreakdownEntry>) || {};
    } else if (e.event_type === "agent_output") {
      const session = getSession(role, repo, e.stage);
      session.items.push({
        type: "output",
        text: (e.data.text as string) || "",
        round: (e.data.round as number) || 0,
        ts: e.timestamp,
      });
    } else if (e.event_type === "agent_tool_call") {
      const session = getSession(role, repo, e.stage);
      const subtype = (e.data.type as string) || "";
      if (subtype === "result") {
        session.items.push({
          type: "tool_result",
          tool: (e.data.tool as string) || "",
          result: (e.data.result as string) || "",
          round: (e.data.round as number) || 0,
          ts: e.timestamp,
        });
      } else {
        session.items.push({
          type: "tool_call",
          tool: (e.data.tool as string) || "",
          input: e.data.input || {},
          round: (e.data.round as number) || 0,
          ts: e.timestamp,
        });
        if (e.data.result_snippet && !subtype) {
          session.items.push({
            type: "tool_result",
            tool: (e.data.tool as string) || "",
            result: (e.data.result_snippet as string) || "",
            round: (e.data.round as number) || 0,
            ts: e.timestamp + 0.001,
          });
        }
      }
    } else if (e.event_type === "agent_nudge") {
      const session = getSession(role, repo, e.stage);
      session.items.push({
        type: "nudge",
        text: (e.data.text as string) || "",
        ts: e.timestamp,
      });
    }
  }

  return sessions;
}
