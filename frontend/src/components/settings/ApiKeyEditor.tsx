import { useCallback, useEffect, useState } from "react";
import type { ApiKeyStatus } from "../../api/types";
import { clearApiKey, getApiKeys, setApiKey } from "../../api/client";

const ROW =
  "flex items-center justify-between px-4 py-3 border-b border-border-subtle last:border-b-0";
const BADGE_BASE = "px-2 py-0.5 text-[10px] rounded font-medium";
const INPUT =
  "bg-surface-raised border border-border-subtle rounded px-3 py-1.5 text-sm text-text w-64 font-mono";

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

function KeyRow({ status, onUpdated }: KeyRowProps) {
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
    <div>
      <div className={ROW}>
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-text w-24">{status.display_name}</span>
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
        <div className="px-4 py-2 bg-bg-card/50 flex items-center gap-2">
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
        <div className="px-4 py-1.5 text-xs text-status-failed">{error}</div>
      )}
    </div>
  );
}

export default function ApiKeyEditor() {
  const [keys, setKeys] = useState<ApiKeyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getApiKeys()
      .then(setKeys)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleUpdated = useCallback((updated: ApiKeyStatus) => {
    setKeys((prev) =>
      prev.map((k) => (k.key_name === updated.key_name ? updated : k)),
    );
  }, []);

  return (
    <div className="mb-8">
      <h2 className="text-sm font-medium text-text-muted mb-3">API Keys</h2>
      {error && (
        <div className="mb-2 px-4 py-2 bg-red-500/10 text-red-400 rounded-lg text-sm">{error}</div>
      )}
      <div className="bg-bg-surface rounded-xl border border-border-subtle overflow-hidden">
        {loading ? (
          <div className="px-4 py-6 text-center text-text-dim text-sm">Loading...</div>
        ) : keys.length === 0 ? (
          <div className="px-4 py-6 text-center text-text-dim text-sm">No API keys registered</div>
        ) : (
          keys.map((k) => (
            <KeyRow key={k.key_name} status={k} onUpdated={handleUpdated} />
          ))
        )}
      </div>
    </div>
  );
}
