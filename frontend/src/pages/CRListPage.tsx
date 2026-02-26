import { useCRList } from "../hooks/useCRList";
import CRCard from "../components/cr/CRCard";

export default function CRListPage() {
  const { runs, loading, error } = useCRList();

  return (
    <div className="max-w-4xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-text">Pipeline Runs</h1>
        <span className="text-xs text-text-dim">
          {runs.length} run{runs.length !== 1 && "s"}
        </span>
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
          <p className="text-base mb-2">No pipeline runs yet</p>
          <p className="text-sm">Trigger a new CR to get started.</p>
        </div>
      )}

      <div className="bg-bg-surface rounded-xl border border-border-subtle overflow-hidden">
        {runs.map((run) => (
          <CRCard key={run.cr_id} run={run} />
        ))}
      </div>
    </div>
  );
}
