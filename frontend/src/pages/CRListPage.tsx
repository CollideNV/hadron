import { useState, useEffect } from "react";
import { useCRList } from "../hooks/useCRList";
import CRCard from "../components/cr/CRCard";
import CRCreationDialog from "../components/cr/CRCreationDialog";
import LiveActivityFeed from "../components/activity/LiveActivityFeed";
import { BTN_ACCENT } from "../utils/styles";

const STATUSES = ["running", "pending", "paused", "completed", "failed"] as const;
const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "cost", label: "Highest cost" },
] as const;

const CHIP_BASE = "px-2.5 py-1 text-[11px] rounded-md cursor-pointer border transition-colors";
const CHIP_ACTIVE = `${CHIP_BASE} bg-accent/15 text-accent border-accent/30`;
const CHIP_INACTIVE = `${CHIP_BASE} bg-transparent text-text-muted border-border-subtle hover:text-text`;

export default function CRListPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState("newest");
  const [dialogOpen, setDialogOpen] = useState(false);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const { runs, loading, error, refresh } = useCRList({
    search: debouncedSearch || undefined,
    status: statusFilter.size > 0 ? Array.from(statusFilter).join(",") : undefined,
    sort,
  });

  const toggleStatus = (s: string) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  return (
    <div className="max-w-4xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold text-text">Pipeline Runs</h1>
        <div className="flex items-center gap-4">
          <span className="text-xs text-text-dim">
            {runs.length} run{runs.length !== 1 && "s"}
          </span>
          <button
            onClick={() => setDialogOpen(true)}
            className={BTN_ACCENT}
          >
            + New CR
          </button>
        </div>
      </div>

      {/* Search + Sort */}
      <div className="flex items-center gap-3 mb-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by title or CR ID..."
          data-testid="cr-search"
          className="flex-1 bg-surface-raised border border-border-subtle rounded px-3 py-1.5 text-sm text-text placeholder:text-text-dim outline-none focus:border-accent/40 transition-colors"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          data-testid="cr-sort"
          className="bg-surface-raised border border-border-subtle rounded px-3 py-1.5 text-sm text-text"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Status filter chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => toggleStatus(s)}
            data-testid={`status-filter-${s}`}
            className={statusFilter.has(s) ? CHIP_ACTIVE : CHIP_INACTIVE}
          >
            {s}
          </button>
        ))}
        {statusFilter.size > 0 && (
          <button
            onClick={() => setStatusFilter(new Set())}
            className="px-2 py-1 text-[11px] text-text-dim hover:text-text cursor-pointer bg-transparent border-none transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {loading && (
        <div className="text-center py-12 text-text-dim">Loading...</div>
      )}

      {error && (
        <div className="bg-status-failed/10 text-status-failed px-4 py-3 rounded-lg text-sm mb-4 border border-status-failed/20">
          {error}
        </div>
      )}

      {!loading && runs.length === 0 && !error && (
        <div className="text-center py-16 text-text-dim">
          <p className="text-base mb-2">No pipeline runs found</p>
          <p className="text-sm">
            {debouncedSearch || statusFilter.size > 0
              ? "Try adjusting your search or filters."
              : "Trigger a new CR to get started."}
          </p>
        </div>
      )}

      <div className="bg-bg-surface rounded-xl border border-border-subtle overflow-hidden">
        {runs.map((run) => (
          <CRCard key={run.cr_id} run={run} />
        ))}
      </div>

      {/* Live activity feed */}
      <div className="mt-6">
        <LiveActivityFeed />
      </div>

      <CRCreationDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={refresh}
      />
    </div>
  );
}
