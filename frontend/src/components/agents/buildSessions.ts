import type { PipelineEvent } from "../../api/types";
import type { AgentSession } from "./types";
import { applyEventToSession } from "./eventToItem";

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
    const d = e.data as Record<string, unknown>;
    const baseKey = `${e.stage}:${d.role || ""}:${d.repo || ""}`;
    // agent_started/agent_completed carry loop_iteration; other events inherit it
    const loop = (d.loop_iteration as number | undefined) ?? currentLoop.get(baseKey) ?? 0;

    if (e.event_type === "agent_started") {
      currentLoop.set(baseKey, loop);
    }

    // Track phase transitions for the phase map
    if (e.event_type === "phase_started") {
      const phase = (d.phase as string) || "";
      currentPhase.set(baseKey, phase);
    } else if (e.event_type === "phase_completed") {
      currentPhase.delete(baseKey);
    }

    const session = getSession(
      (d.role as string) || "",
      (d.repo as string) || "",
      e.stage,
      loop,
    );

    applyEventToSession(e, session, currentPhase.get(baseKey));
  }

  return sessions;
}
