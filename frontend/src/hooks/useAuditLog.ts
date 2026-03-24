import { useEffect, useState, useCallback } from "react";
import { getAuditLog } from "../api/client";
import type { AuditLogEntry } from "../api/types";

export function useAuditLog() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAuditLog({
        page,
        page_size: 50,
        action: action || undefined,
      });
      setItems(data.items);
      setTotal(data.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, [page, action]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSetAction = useCallback((a: string) => {
    setAction(a);
    setPage(1);
  }, []);

  return { items, total, page, setPage, action, setAction: handleSetAction, loading, error };
}
