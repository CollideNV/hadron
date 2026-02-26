import { useState, useEffect, useRef, useCallback } from "react";
import { getWorkerLogs } from "../../api/client";

interface LogsPanelProps {
  crId: string;
  pipelineStatus: string;
}

export default function LogsPanel({ crId, pipelineStatus }: LogsPanelProps) {
  const [logs, setLogs] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filter, setFilter] = useState("");
  const scrollRef = useRef<HTMLPreElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const text = await getWorkerLogs(crId);
      setLogs(text);
    } catch {
      // Silently ignore — logs may not be available yet
    } finally {
      setLoading(false);
    }
  }, [crId]);

  // Initial fetch
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Auto-refresh while pipeline is running
  useEffect(() => {
    if (
      autoRefresh &&
      (pipelineStatus === "running" || pipelineStatus === "connecting")
    ) {
      intervalRef.current = setInterval(fetchLogs, 5000);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    }
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, [autoRefresh, pipelineStatus, fetchLogs]);

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const filteredLines = filter
    ? logs
        .split("\n")
        .filter((line) => line.toLowerCase().includes(filter.toLowerCase()))
        .join("\n")
    : logs;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-subtle flex items-center gap-3 flex-shrink-0">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Worker Logs
        </h3>
        <div className="flex-1" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter..."
          className="bg-bg border border-border-subtle rounded px-2 py-0.5 text-[10px] text-text placeholder:text-text-dim focus:outline-none focus:border-accent w-32"
        />
        <label className="flex items-center gap-1 text-[10px] text-text-dim cursor-pointer">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="w-3 h-3"
          />
          Auto-refresh
        </label>
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="text-[10px] text-accent hover:text-accent/80 cursor-pointer bg-transparent border-none disabled:opacity-50 transition-colors"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>
      <div className="flex-1 overflow-hidden">
        <pre
          ref={scrollRef}
          className="h-full overflow-y-auto px-4 py-2 text-[11px] font-mono text-text-muted leading-relaxed bg-[#0d1117] m-0 whitespace-pre-wrap break-all"
        >
          {filteredLines || (
            <span className="text-text-dim">
              {loading ? "Loading logs..." : "No logs available yet."}
            </span>
          )}
        </pre>
      </div>
    </div>
  );
}
