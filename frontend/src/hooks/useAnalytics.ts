import { useEffect, useState, useCallback } from "react";
import { getAnalyticsSummary, getAnalyticsCost } from "../api/client";
import type { AnalyticsSummary, AnalyticsCost } from "../api/types";
import { POLL_INTERVAL_MS } from "../utils/constants";

export function useAnalyticsSummary(days = 30, pollInterval = POLL_INTERVAL_MS) {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await getAnalyticsSummary(days);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const timer = setInterval(refresh, pollInterval);
    return () => clearInterval(timer);
  }, [refresh, pollInterval]);

  return { data, loading, error, refresh };
}

export function useAnalyticsCost(groupBy = "stage", pollInterval = POLL_INTERVAL_MS) {
  const [data, setData] = useState<AnalyticsCost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await getAnalyticsCost(groupBy);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cost data");
    } finally {
      setLoading(false);
    }
  }, [groupBy]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const timer = setInterval(refresh, pollInterval);
    return () => clearInterval(timer);
  }, [refresh, pollInterval]);

  return { data, loading, error, refresh };
}
