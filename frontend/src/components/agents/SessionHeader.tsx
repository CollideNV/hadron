import type { AgentSession } from "./types";
import { formatModelName, formatCost } from "../../utils/format";

interface SessionHeaderProps {
  session: AgentSession;
  isActive: boolean;
}

export default function SessionHeader({ session, isActive }: SessionHeaderProps) {
  return (
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
      {(session.models && session.models.length > 1 ? session.models : session.model ? [session.model] : []).map((m) => (
        <span key={m} className="text-[10px] text-text-muted font-mono bg-bg-surface border border-border-subtle rounded px-1 py-0.5">
          {formatModelName(m)}
        </span>
      ))}
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
      {session.throttleCount > 0 && (
        <span className="text-[10px] text-status-error" title={`Throttled ${session.throttleCount} time(s), lost ${session.throttleSeconds.toFixed(0)}s`}>
          {session.throttleSeconds.toFixed(0)}s throttled
        </span>
      )}
      {session.costUsd > 0 && (
        <span className="text-[10px] text-accent ml-auto">
          {formatCost(session.costUsd, 3)}
        </span>
      )}
    </div>
  );
}
