import { useEffect, useState, useCallback } from "react";
import { listPipelines } from "../api/client";
import type { ListPipelinesParams } from "../api/client";
import type { CRRun } from "../api/types";
import { POLL_INTERVAL_MS } from "../utils/constants";

export function useCRList(
  params: ListPipelinesParams = {},
  pollInterval = POLL_INTERVAL_MS,
) {
  const [runs, setRuns] = useState<CRRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Serialize params for stable dependency tracking
  const paramsKey = JSON.stringify(params);

  const refresh = useCallback(async () => {
    try {
      const data = await listPipelines(JSON.parse(paramsKey));
      setRuns(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pipelines");
    } finally {
      setLoading(false);
    }
  }, [paramsKey]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const timer = setInterval(refresh, pollInterval);
    return () => clearInterval(timer);
  }, [refresh, pollInterval]);

  return { runs, loading, error, refresh };
}
