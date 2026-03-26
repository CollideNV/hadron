import { Link } from "react-router-dom";
import { useAuditLog } from "../hooks/useAuditLog";

const ACTION_TYPES = [
  "backend_templates_updated",
  "default_template_updated",
  "pipeline_defaults_updated",
  "prompt_template_updated",
];

const CHIP_BASE = "px-2.5 py-1 text-[11px] rounded-md cursor-pointer border transition-colors";
const CHIP_ACTIVE = `${CHIP_BASE} bg-accent/15 text-accent border-accent/30`;
const CHIP_INACTIVE = `${CHIP_BASE} bg-transparent text-text-muted border-border-subtle hover:text-text`;

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function AuditLogPage() {
  const { items, total, page, setPage, action, setAction, loading, error } = useAuditLog();
  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="max-w-4xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-text">Audit Log</h1>
        <span className="text-xs text-text-dim">
          {total} entr{total !== 1 ? "ies" : "y"}
        </span>
      </div>

      {/* Action filter chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => setAction("")}
          className={!action ? CHIP_ACTIVE : CHIP_INACTIVE}
          data-testid="audit-filter-all"
        >
          All
        </button>
        {ACTION_TYPES.map((a) => (
          <button
            key={a}
            onClick={() => setAction(a === action ? "" : a)}
            className={action === a ? CHIP_ACTIVE : CHIP_INACTIVE}
            data-testid={`audit-filter-${a}`}
          >
            {a.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-status-failed/10 text-status-failed px-4 py-3 rounded-lg text-sm mb-4 border border-status-failed/20">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-center py-12 text-text-dim">Loading...</div>
      )}

      {!loading && items.length === 0 && !error && (
        <div className="text-center py-16 text-text-dim">
          <p className="text-base mb-2">No audit entries found</p>
          <p className="text-sm">Actions like settings changes and pipeline triggers will appear here.</p>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="bg-bg-surface rounded-xl border border-border-subtle overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg-card text-text-dim text-[10px] uppercase tracking-wider">
                <th className="text-left px-4 py-2 font-medium">Timestamp</th>
                <th className="text-left px-4 py-2 font-medium">Action</th>
                <th className="text-left px-4 py-2 font-medium">CR</th>
                <th className="text-left px-4 py-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody>
              {items.map((entry) => (
                <tr
                  key={entry.id}
                  className="border-t border-border-subtle hover:bg-bg-card/50 transition-colors"
                >
                  <td className="px-4 py-2 text-text-muted font-mono text-[11px] whitespace-nowrap">
                    {formatTimestamp(entry.timestamp)}
                  </td>
                  <td className="px-4 py-2">
                    <span className="inline-block px-2 py-0.5 text-[10px] rounded bg-accent/10 text-accent font-medium">
                      {entry.action.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-text-muted font-mono text-[11px]">
                    {entry.cr_id ? (
                      <Link to={`/cr/${entry.cr_id}`} className="text-accent hover:underline">
                        {entry.cr_id}
                      </Link>
                    ) : (
                      <span className="text-text-dim">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-text-dim text-[11px] font-mono max-w-xs truncate">
                    {entry.details ? JSON.stringify(entry.details) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 text-sm rounded-md border border-border-subtle text-text-muted hover:text-text transition-colors cursor-pointer bg-transparent disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-xs text-text-dim">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 text-sm rounded-md border border-border-subtle text-text-muted hover:text-text transition-colors cursor-pointer bg-transparent disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
