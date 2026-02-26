import { useState, useRef, useEffect, useCallback } from "react";
import { sendNudge } from "../../api/client";
import type { PipelineEvent } from "../../api/types";

interface AgentActivityPanelProps {
  crId: string;
  events: PipelineEvent[];
  toolCalls: PipelineEvent[];
  agentOutputs: PipelineEvent[];
  agentNudges: PipelineEvent[];
  pipelineStatus: string;
}

interface AgentSession {
  role: string;
  repo: string;
  stage: string;
  completed: boolean;
  model?: string;
  allowedTools?: string[];
  /** Ordered conversation items built from events */
  items: ConversationItem[];
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  roundCount: number;
  conversationKey?: string;
}

type ConversationItem =
  | { type: "output"; text: string; round: number; ts: number }
  | { type: "tool_call"; tool: string; input: unknown; round: number; ts: number }
  | { type: "tool_result"; tool: string; result: string; round: number; ts: number }
  | { type: "nudge"; text: string; ts: number };

function buildSessions(
  events: PipelineEvent[],
  toolCalls: PipelineEvent[],
  agentOutputs: PipelineEvent[],
  agentNudges: PipelineEvent[],
): AgentSession[] {
  const sessions: AgentSession[] = [];
  const sessionMap = new Map<string, AgentSession>();

  // Helper to find or create a session
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
      };
      sessionMap.set(key, session);
      sessions.push(session);
    }
    return session;
  };

  // Process all events in timestamp order
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
      session.allowedTools = (e.data.allowed_tools as string[]) || undefined;
    } else if (e.event_type === "agent_completed") {
      const session = getSession(role, repo, e.stage);
      session.completed = true;
      session.inputTokens = (e.data.input_tokens as number) || 0;
      session.outputTokens = (e.data.output_tokens as number) || 0;
      session.costUsd = (e.data.cost_usd as number) || 0;
      session.roundCount = (e.data.round_count as number) || 0;
      session.conversationKey = (e.data.conversation_key as string) || undefined;
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
        // "call" or legacy (no type field)
        session.items.push({
          type: "tool_call",
          tool: (e.data.tool as string) || "",
          input: e.data.input || {},
          round: (e.data.round as number) || 0,
          ts: e.timestamp,
        });
        // For legacy events that have result_snippet
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

function ToolCallDetail({
  item,
}: {
  item: Extract<ConversationItem, { type: "tool_call" }>;
}) {
  const [expanded, setExpanded] = useState(false);
  const inputStr =
    typeof item.input === "string"
      ? item.input
      : JSON.stringify(item.input, null, 2);
  const summary =
    typeof item.input === "object" && item.input !== null
      ? Object.entries(item.input as Record<string, unknown>)
          .map(([k, v]) => {
            const s = String(v);
            return `${k}: ${s.length > 60 ? s.slice(0, 60) + "..." : s}`;
          })
          .join(", ")
      : inputStr.slice(0, 100);

  return (
    <div className="border border-border-subtle rounded-md bg-bg/50 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left cursor-pointer bg-transparent border-none px-2.5 py-1.5 text-inherit"
      >
        <span className="text-accent/70">&#128295;</span>
        <span className="font-mono font-medium text-accent text-[11px]">
          {item.tool}
        </span>
        <span className="text-text-dim truncate flex-1 text-[10px]">
          {summary}
        </span>
        <span className="text-text-dim text-[10px] flex-shrink-0">
          {expanded ? "collapse" : "expand"}
        </span>
      </button>
      {expanded && (
        <div className="px-2.5 pb-2 space-y-1 text-[10px] border-t border-border-subtle pt-1.5">
          <div>
            <span className="text-text-dim font-semibold">Input:</span>
            <pre className="mt-0.5 text-text-muted whitespace-pre-wrap break-all bg-bg-surface rounded p-1.5 max-h-48 overflow-y-auto">
              {inputStr}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function ToolResultDetail({
  item,
}: {
  item: Extract<ConversationItem, { type: "tool_result" }>;
}) {
  const [expanded, setExpanded] = useState(false);
  const preview = item.result.slice(0, 80).replace(/\n/g, " ");

  return (
    <div className="border border-border-subtle rounded-md bg-bg/50 text-xs ml-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left cursor-pointer bg-transparent border-none px-2.5 py-1 text-inherit"
      >
        <span className="text-text-dim text-[10px]">&#8627;</span>
        <span className="font-mono text-text-dim text-[10px]">
          {item.tool}
        </span>
        <span className="text-text-dim truncate flex-1 text-[10px]">
          {preview}
          {item.result.length > 80 ? "..." : ""}
        </span>
        <span className="text-text-dim text-[10px] flex-shrink-0">
          {expanded ? "collapse" : "expand"}
        </span>
      </button>
      {expanded && (
        <div className="px-2.5 pb-2 text-[10px] border-t border-border-subtle pt-1.5">
          <pre className="text-text-muted whitespace-pre-wrap break-all bg-bg-surface rounded p-1.5 max-h-64 overflow-y-auto">
            {item.result}
          </pre>
        </div>
      )}
    </div>
  );
}

function NudgeInput({
  crId,
  role,
}: {
  crId: string;
  role: string;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  const handleSend = useCallback(async () => {
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      await sendNudge(crId, role, text.trim());
      setText("");
    } catch (e) {
      console.error("Failed to send nudge:", e);
    } finally {
      setSending(false);
    }
  }, [crId, role, text, sending]);

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-t border-border-subtle bg-bg-surface">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder="Guide this agent..."
        className="flex-1 bg-bg border border-border-subtle rounded px-2 py-1 text-xs text-text placeholder:text-text-dim focus:outline-none focus:border-accent"
        disabled={sending}
      />
      <button
        onClick={handleSend}
        disabled={!text.trim() || sending}
        className="px-2.5 py-1 text-[11px] font-medium bg-accent text-white rounded cursor-pointer border-none disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/90 transition-colors"
      >
        Send
      </button>
    </div>
  );
}

function AgentConversationView({
  session,
  crId,
  pipelineStatus,
}: {
  session: AgentSession;
  crId: string;
  pipelineStatus: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session.items.length]);

  const isActive =
    !session.completed &&
    (pipelineStatus === "running" || pipelineStatus === "connecting");

  const tokenInfo = session.inputTokens
    ? `${(session.inputTokens / 1000).toFixed(1)}k / ${(session.outputTokens / 1000).toFixed(1)}k tok`
    : "";

  return (
    <div className="flex flex-col h-full">
      {/* Session header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle bg-bg-surface flex-shrink-0">
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            isActive
              ? "bg-accent animate-pulse-glow"
              : session.completed
                ? "bg-status-completed"
                : "bg-text-dim"
          }`}
        />
        <span className="text-xs font-medium text-text">
          {session.role.replace(/_/g, " ")}
        </span>
        {session.repo && (
          <span className="text-[10px] text-text-dim font-mono">
            ({session.repo})
          </span>
        )}
        {session.roundCount > 0 && (
          <span className="text-[10px] text-text-dim">
            round {session.roundCount}
          </span>
        )}
        {session.costUsd > 0 && (
          <span className="text-[10px] text-accent ml-auto">
            ${session.costUsd.toFixed(3)}
          </span>
        )}
      </div>

      {/* Conversation */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-3 py-2 space-y-2"
      >
        {session.items.length === 0 && isActive && (
          <p className="text-xs text-text-dim py-4 text-center animate-pulse">
            Agent is thinking...
          </p>
        )}
        {session.items.map((item, i) => {
          if (item.type === "output") {
            return (
              <div key={i} className="animate-fade-in">
                <div className="flex items-start gap-2">
                  <span className="text-[11px] flex-shrink-0 mt-0.5">&#129302;</span>
                  <p className="text-xs text-text leading-relaxed whitespace-pre-wrap">
                    {item.text}
                  </p>
                </div>
              </div>
            );
          }
          if (item.type === "tool_call") {
            return (
              <div key={i} className="animate-fade-in">
                <ToolCallDetail item={item} />
              </div>
            );
          }
          if (item.type === "tool_result") {
            return (
              <div key={i} className="animate-fade-in">
                <ToolResultDetail item={item} />
              </div>
            );
          }
          if (item.type === "nudge") {
            return (
              <div key={i} className="animate-fade-in">
                <div className="flex items-start gap-2">
                  <span className="text-[11px] flex-shrink-0 mt-0.5">&#128100;</span>
                  <p className="text-xs text-text leading-relaxed bg-accent/10 rounded px-2 py-1 border border-accent/20">
                    {item.text}
                  </p>
                </div>
              </div>
            );
          }
          return null;
        })}
      </div>

      {/* Token info footer */}
      {tokenInfo && (
        <div className="px-3 py-1 border-t border-border-subtle text-[10px] text-text-dim text-right flex-shrink-0">
          {tokenInfo}
        </div>
      )}

      {/* Nudge input — only for active sessions */}
      {isActive && (
        <NudgeInput crId={crId} role={session.role} />
      )}
    </div>
  );
}

function AgentSessionList({
  sessions,
  selectedIndex,
  onSelect,
}: {
  sessions: AgentSession[];
  selectedIndex: number;
  onSelect: (i: number) => void;
}) {
  return (
    <div className="border-r border-border-subtle overflow-y-auto">
      {sessions.map((session, i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          className={`w-full text-left px-3 py-2 border-b border-border-subtle cursor-pointer bg-transparent border-x-0 border-t-0 transition-colors ${
            i === selectedIndex
              ? "bg-accent/10"
              : "hover:bg-bg-surface"
          }`}
        >
          <div className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                session.completed
                  ? "bg-status-completed"
                  : "bg-accent animate-pulse-glow"
              }`}
            />
            <span className="text-[11px] font-medium text-text truncate">
              {session.role.replace(/_/g, " ")}
            </span>
          </div>
          {session.repo && (
            <div className="text-[9px] text-text-dim font-mono ml-3 truncate">
              {session.repo}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}

export default function AgentActivityPanel({
  crId,
  events,
  toolCalls,
  agentOutputs,
  agentNudges,
  pipelineStatus,
}: AgentActivityPanelProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const sessions = buildSessions(events, toolCalls, agentOutputs, agentNudges);

  // Auto-select the latest active session
  useEffect(() => {
    let lastActive = -1;
    for (let i = sessions.length - 1; i >= 0; i--) {
      if (!sessions[i].completed) {
        lastActive = i;
        break;
      }
    }
    if (lastActive >= 0 && lastActive !== selectedIndex) {
      setSelectedIndex(lastActive);
    }
  }, [sessions.length]);

  const selectedSession = sessions[selectedIndex];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-subtle flex-shrink-0">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Agent Activity
        </h3>
      </div>
      {sessions.length === 0 ? (
        <p className="text-xs text-text-dim py-4 text-center flex-1">
          No agent activity yet
        </p>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          {/* Session sidebar */}
          <div className="w-36 flex-shrink-0">
            <AgentSessionList
              sessions={sessions}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
            />
          </div>
          {/* Conversation view */}
          <div className="flex-1 overflow-hidden">
            {selectedSession ? (
              <AgentConversationView
                session={selectedSession}
                crId={crId}
                pipelineStatus={pipelineStatus}
              />
            ) : (
              <p className="text-xs text-text-dim py-4 text-center">
                Select a session
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
