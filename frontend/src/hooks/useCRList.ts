import { useEffect, useState, useCallback } from "react";
import { listPipelines } from "../api/client";
import type { CRRun } from "../api/types";

export function useCRList(pollInterval = 5000) {
  const [runs, setRuns] = useState<CRRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listPipelines();
      setRuns(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pipelines");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, pollInterval);
    return () => clearInterval(timer);
  }, [refresh, pollInterval]);

  return { runs, loading, error, refresh };
}
