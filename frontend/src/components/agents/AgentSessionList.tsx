import type { AgentSession } from "./types";
import { formatModelName, formatModelNameShort } from "../../utils/format";

interface AgentSessionListProps {
  sessions: AgentSession[];
  selectedIndex: number;
  onSelect: (i: number) => void;
  /** When true, insert round headers between groups of different loopIteration values. */
  showRoundHeaders?: boolean;
}

function SessionRow({
  session,
  selected,
  onClick,
  hideLoopSuffix,
}: {
  session: AgentSession;
  selected: boolean;
  onClick: () => void;
  hideLoopSuffix?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 border-b border-border-subtle cursor-pointer bg-transparent border-x-0 border-t-0 transition-colors ${
        selected ? "bg-accent/10" : "hover:bg-bg-surface"
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
          {!hideLoopSuffix && session.loopIteration > 0 && (
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
  );
}

export default function AgentSessionList({
  sessions,
  selectedIndex,
  onSelect,
  showRoundHeaders = false,
}: AgentSessionListProps) {
  // Detect whether we have multiple rounds (only insert headers if so)
  const hasMultipleRounds =
    showRoundHeaders && new Set(sessions.map((s) => s.loopIteration)).size > 1;

  let lastRound = -1;

  return (
    <div className="border-r border-border-subtle overflow-y-auto">
      {sessions.map((session, i) => {
        const roundChanged = hasMultipleRounds && session.loopIteration !== lastRound;
        lastRound = session.loopIteration;

        return (
          <div key={`${session.stage}:${session.role}:${session.repo}:${session.loopIteration}`}>
            {roundChanged && (
              <div className="px-3 py-1.5 bg-bg border-b border-border-subtle" data-testid={`round-header-${session.loopIteration + 1}`}>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-text-dim">
                  Review {session.loopIteration + 1}
                </span>
              </div>
            )}
            <SessionRow
              session={session}
              selected={i === selectedIndex}
              onClick={() => onSelect(i)}
              hideLoopSuffix={hasMultipleRounds}
            />
          </div>
        );
      })}
    </div>
  );
}
