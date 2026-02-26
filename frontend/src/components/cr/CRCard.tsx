import { Link } from "react-router-dom";
import type { CRRun } from "../../api/types";
import CRStatusBadge from "./CRStatusBadge";

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function CRCard({ run }: { run: CRRun }) {
  return (
    <Link
      to={`/cr/${run.cr_id}`}
      className="block no-underline text-inherit hover:bg-bg-card-hover transition-colors"
    >
      <div className="px-5 py-4 flex items-center gap-4 border-b border-border-subtle">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-[11px] text-text-dim">
              {run.cr_id}
            </span>
            <CRStatusBadge status={run.status} />
          </div>
          <p className="mt-1 text-sm font-medium text-text truncate">
            {run.title || "Untitled CR"}
          </p>
        </div>
        <div className="text-right text-[11px] text-text-dim whitespace-nowrap">
          {run.cost_usd > 0 && (
            <div className="font-mono text-accent/80">
              ${run.cost_usd.toFixed(4)}
            </div>
          )}
          <div className="mt-0.5">{relativeTime(run.created_at)}</div>
        </div>
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          className="text-text-dim flex-shrink-0"
        >
          <path
            d="M6 4l4 4-4 4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </Link>
  );
}
