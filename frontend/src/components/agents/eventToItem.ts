import type { PipelineEvent } from "../../api/types";
import type { AgentSession, ConversationItem } from "./types";

/** Loose accessor for event data fields that exist on most but not all event types. */
type AnyEventData = Record<string, unknown>;

/**
 * Processes a single pipeline event and mutates the given session in place,
 * appending conversation items and/or updating session metadata.
 *
 * Returns the current phase string (or undefined) for the base key so the
 * caller can maintain the phase-tracking map.
 *
 * @param phaseForKey  The current phase associated with this event's base key
 *                     (stage:role:repo), or undefined if no phase is active.
 */
export function applyEventToSession(
  e: PipelineEvent,
  session: AgentSession,
  phaseForKey: string | undefined,
): void {
  const d = e.data as AnyEventData;

  if (e.event_type === "agent_started") {
    session.model = (d.model as string) || undefined;
    session.models = (d.models as string[]) || undefined;
    session.allowedTools = (d.allowed_tools as string[]) || undefined;
    session.completed = false;
  } else if (e.event_type === "agent_completed") {
    session.completed = true;
    session.model = session.model || (d.model as string) || undefined;
    session.conversationKey = (d.conversation_key as string) || undefined;
    session.inputTokens += (d.input_tokens as number) || 0;
    session.outputTokens += (d.output_tokens as number) || 0;
    session.costUsd += (d.cost_usd as number) || 0;
    session.roundCount += (d.round_count as number) || 0;
    session.throttleCount += (d.throttle_count as number) || 0;
    session.throttleSeconds += (d.throttle_seconds as number) || 0;
    mergeModelBreakdown(session, d);
  } else if (e.event_type === "agent_prompt") {
    if (!session.items.some((i) => i.type === "prompt")) {
      session.items.push({
        type: "prompt",
        text: (d.text as string) || "",
        ts: e.timestamp,
      });
    }
  } else if (e.event_type === "phase_started") {
    const phase = (d.phase as string) || "";
    session.items.push({
      type: "phase_started",
      phase,
      model: (d.model as string) || "",
      ts: e.timestamp,
    });
  } else if (e.event_type === "phase_completed") {
    // Phase stats are only used for live display while agent is running.
    // agent_completed is the authoritative source for final costs.
    // Skip accumulation -- agent_completed handles totals correctly.
  } else if (e.event_type === "agent_output") {
    session.items.push({
      type: "output",
      text: (d.text as string) || "",
      round: (d.round as number) || 0,
      ts: e.timestamp,
      phase: phaseForKey,
    });
  } else if (e.event_type === "agent_tool_call") {
    appendToolCallItems(session.items, e, d, phaseForKey);
  } else if (e.event_type === "agent_nudge") {
    session.items.push({
      type: "nudge",
      text: (d.text as string) || "",
      ts: e.timestamp,
      phase: phaseForKey,
    });
  }
}

function mergeModelBreakdown(session: AgentSession, d: AnyEventData): void {
  const breakdown = (d.model_breakdown || {}) as Record<string, AnyEventData>;
  for (const [model, stats] of Object.entries(breakdown)) {
    const existing = session.modelBreakdown[model] || {
      input_tokens: 0, output_tokens: 0, cost_usd: 0,
      throttle_count: 0, throttle_seconds: 0, api_calls: 0,
    };
    session.modelBreakdown[model] = {
      input_tokens: existing.input_tokens + ((stats.input_tokens as number) || 0),
      output_tokens: existing.output_tokens + ((stats.output_tokens as number) || 0),
      cost_usd: existing.cost_usd + ((stats.cost_usd as number) || 0),
      throttle_count: existing.throttle_count + ((stats.throttle_count as number) || 0),
      throttle_seconds: existing.throttle_seconds + ((stats.throttle_seconds as number) || 0),
      api_calls: existing.api_calls + ((stats.api_calls as number) || 0),
    };
  }
}

function appendToolCallItems(
  items: ConversationItem[],
  e: PipelineEvent,
  d: AnyEventData,
  phase: string | undefined,
): void {
  const subtype = (d.type as string) || "";
  if (subtype === "result") {
    items.push({
      type: "tool_result",
      tool: (d.tool as string) || "",
      result: (d.result as string) || "",
      round: (d.round as number) || 0,
      ts: e.timestamp,
      phase,
    });
  } else {
    items.push({
      type: "tool_call",
      tool: (d.tool as string) || "",
      input: d.input || {},
      round: (d.round as number) || 0,
      ts: e.timestamp,
      phase,
    });
    if (d.result_snippet && !subtype) {
      items.push({
        type: "tool_result",
        tool: (d.tool as string) || "",
        result: (d.result_snippet as string) || "",
        round: (d.round as number) || 0,
        ts: e.timestamp + 0.001,
        phase,
      });
    }
  }
}
