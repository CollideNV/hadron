import type { AgentSession } from "./types";
import { formatModelName, formatModelNameShort } from "../../utils/format";

interface AgentSessionListProps {
  sessions: AgentSession[];
  selectedIndex: number;
  onSelect: (i: number) => void;
}

export default function AgentSessionList({
  sessions,
  selectedIndex,
  onSelect,
}: AgentSessionListProps) {
  return (
    <div className="border-r border-border-subtle overflow-y-auto">
      {sessions.map((session, i) => (
        <button
          key={`${session.stage}:${session.role}:${session.repo}:${session.loopIteration}`}
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
              {session.loopIteration > 0 && (
                <span className="text-text-dim ml-1 font-normal">#{session.loopIteration + 1}</span>
              )}
            </span>
          </div>
          {(session.repo || session.model) && (
            <div className="text-[9px] text-text-dim font-mono ml-3 truncate">
              {session.models && session.models.length > 1 ? (
                <span className="text-text-muted">
                  {session.models.map(m => formatModelNameShort(m)).join("/")}
                </span>
              ) : session.model ? (
                <span className="text-text-muted">
                  {formatModelName(session.model)}
                </span>
              ) : null}
              {session.repo && (session.models?.length || session.model) && " · "}
              {session.repo}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
