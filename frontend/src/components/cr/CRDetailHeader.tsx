import { Link } from "react-router-dom";
import CRStatusBadge from "./CRStatusBadge";
import CostTracker from "../cost/CostTracker";
import InterventionModal from "../intervention/InterventionModal";
import ResumeModal from "../intervention/ResumeModal";
import type { PipelineEvent } from "../../api/types";

interface CRDetailHeaderProps {
  crId: string;
  title: string;
  displayStatus: string;
  costUsd: number;
  events?: PipelineEvent[];
  showLogs: boolean;
  onToggleLogs: () => void;
}

export default function CRDetailHeader({
  crId,
  title,
  displayStatus,
  costUsd,
  events,
  showLogs,
  onToggleLogs,
}: CRDetailHeaderProps) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 bg-bg-surface border-b border-border-subtle">
      <div className="flex items-center gap-3 min-w-0">
        <Link
          to="/"
          className="text-text-dim hover:text-text no-underline text-sm transition-colors"
        >
          &larr;
        </Link>
        <span className="font-mono text-[11px] text-text-dim">{crId}</span>
        <span className="text-sm font-medium text-text truncate">
          {title}
        </span>
        <CRStatusBadge status={displayStatus} />
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleLogs}
          data-testid="logs-toggle"
          className={`px-2.5 py-1 text-[11px] font-medium rounded cursor-pointer border transition-colors ${
            showLogs
              ? "bg-accent/15 text-accent border-accent/30"
              : "bg-transparent text-text-dim border-border-subtle hover:text-text hover:border-border-subtle"
          }`}
        >
          Logs
        </button>
        <CostTracker costUsd={costUsd} events={events} />
        <ResumeModal crId={crId} status={displayStatus} />
        <InterventionModal crId={crId} />
      </div>
    </div>
  );
}
