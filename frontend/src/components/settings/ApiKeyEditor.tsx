import { useCallback, useEffect, useState } from "react";
import type { ApiKeyStatus } from "../../api/types";
import { clearApiKey, getApiKeys, setApiKey } from "../../api/client";

const BADGE_BASE = "px-2 py-0.5 text-[10px] rounded font-medium";
const INPUT =
  "bg-surface-raised border border-border-subtle rounded px-3 py-1.5 text-sm text-text w-64 font-mono";

/** Map backend slug to the corresponding API key name. */
const BACKEND_TO_KEY: Record<string, string> = {
  claude: "anthropic_api_key",
  openai: "openai_api_key",
  gemini: "gemini_api_key",
};

function sourceBadge(source: ApiKeyStatus["source"]) {
  switch (source) {
    case "database":
      return <span className={`${BADGE_BASE} bg-accent/10 text-accent`}>Database</span>;
    case "environment":
      return <span className={`${BADGE_BASE} bg-blue-500/10 text-blue-400`}>Environment</span>;
    default:
      return <span className={`${BADGE_BASE} bg-surface-raised text-text-dim`}>Not set</span>;
  }
}

interface KeyRowProps {
  status: ApiKeyStatus;
  onUpdated: (updated: ApiKeyStatus) => void;
}

/** A single API key row — shows masked value, source badge, set/clear buttons. */
export function KeyRow({ status, onUpdated }: KeyRowProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = useCallback(async () => {
    if (!value.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await setApiKey(status.key_name, value);
      onUpdated(updated);
      setEditing(false);
      setValue("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [status.key_name, value, onUpdated]);

  const handleClear = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await clearApiKey(status.key_name);
      onUpdated(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [status.key_name, onUpdated]);

  const handleCancel = useCallback(() => {
    setEditing(false);
    setValue("");
    setError(null);
  }, []);

  return (
    <div className="p-3 rounded-lg bg-surface-raised border border-border-subtle">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xs font-medium text-text-muted">API Key</span>
          {status.is_configured ? (
            <span className="text-sm font-mono text-text-muted" data-testid={`masked-${status.key_name}`}>
              {status.masked_value}
            </span>
          ) : (
            <span className="text-sm text-text-dim italic">Not configured</span>
          )}
          {sourceBadge(status.source)}
        </div>
        <div className="flex items-center gap-2">
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="px-2.5 py-1 text-[11px] rounded-md border border-border-subtle text-text-muted hover:text-text transition-colors cursor-pointer bg-transparent"
              data-testid={`set-${status.key_name}`}
            >
              {status.is_configured ? "Update" : "Set Key"}
            </button>
          )}
          {status.source === "database" && !editing && (
            <button
              onClick={handleClear}
              disabled={saving}
              className="px-2.5 py-1 text-[11px] rounded-md border border-status-failed/30 text-status-failed/70 hover:text-status-failed transition-colors cursor-pointer bg-transparent"
              data-testid={`clear-${status.key_name}`}
            >
              Clear
            </button>
          )}
        </div>
      </div>
      {editing && (
        <div className="mt-2 flex items-center gap-2">
          <input
            type="password"
            placeholder="Paste API key..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className={INPUT}
            autoFocus
            data-testid={`input-${status.key_name}`}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
              if (e.key === "Escape") handleCancel();
            }}
          />
          <button
            onClick={handleSave}
            disabled={saving || !value.trim()}
            className="px-3 py-1.5 text-xs rounded-md bg-accent text-bg font-medium cursor-pointer border-none disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid={`save-${status.key_name}`}
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            onClick={handleCancel}
            className="px-3 py-1.5 text-xs rounded-md border border-border-subtle text-text-muted cursor-pointer bg-transparent"
          >
            Cancel
          </button>
        </div>
      )}
      {error && (
        <div className="mt-1.5 text-xs text-status-failed">{error}</div>
      )}
    </div>
  );
}

/** Hook that loads API key statuses and provides an updater. */
export function useApiKeys() {
  const [keys, setKeys] = useState<ApiKeyStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getApiKeys()
      .then(setKeys)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleUpdated = useCallback((updated: ApiKeyStatus) => {
    setKeys((prev) =>
      prev.map((k) => (k.key_name === updated.key_name ? updated : k)),
    );
  }, []);

  return { keys, loading, handleUpdated };
}

/** Find the ApiKeyStatus for a given backend slug. */
export function keyForBackend(keys: ApiKeyStatus[], backend: string): ApiKeyStatus | undefined {
  const keyName = BACKEND_TO_KEY[backend];
  return keyName ? keys.find((k) => k.key_name === keyName) : undefined;
}
