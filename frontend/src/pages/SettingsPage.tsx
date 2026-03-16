import { useCallback, useEffect, useState } from "react";
import type { BackendModels, ModelSettings } from "../api/types";
import { getAvailableBackends, getModelSettings, updateModelSettings } from "../api/client";
import ModelGrid from "../components/settings/ModelGrid";

export default function SettingsPage() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [savedSettings, setSavedSettings] = useState<ModelSettings | null>(null);
  const [backends, setBackends] = useState<BackendModels[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getModelSettings(), getAvailableBackends()])
      .then(([s, b]) => {
        setSettings(s);
        setSavedSettings(s);
        setBackends(b);
      })
      .catch((e) => setError(e.message));
  }, []);

  const handleSave = useCallback(async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateModelSettings(settings);
      setSettings(updated);
      setSavedSettings(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [settings]);

  const handleDiscard = useCallback(() => {
    if (savedSettings) setSettings(savedSettings);
  }, [savedSettings]);

  const dirty = settings !== null && savedSettings !== null && JSON.stringify(settings) !== JSON.stringify(savedSettings);

  if (!settings) {
    return (
      <div className="p-8">
        {error ? (
          <div className="px-4 py-2 bg-red-500/10 text-red-400 rounded-lg text-sm">{error}</div>
        ) : (
          <span className="text-text-dim text-sm">Loading settings...</span>
        )}
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {error && (
        <div className="mb-4 px-4 py-2 bg-red-500/10 text-red-400 rounded-lg text-sm">{error}</div>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-text">Model Settings</h1>
        <div className="flex items-center gap-3">
          {dirty && (
            <button
              onClick={handleDiscard}
              className="px-3 py-1.5 text-sm rounded-md border border-border-subtle text-text-muted hover:text-text transition-colors cursor-pointer bg-transparent"
            >
              Discard
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!dirty || saving}
            className={`px-4 py-1.5 text-sm rounded-md font-medium transition-colors cursor-pointer border-none ${
              dirty
                ? "bg-accent text-bg hover:bg-accent/90"
                : "bg-surface-raised text-text-dim cursor-not-allowed"
            }`}
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>

      {/* Default backend */}
      <div className="mb-8">
        <label className="block text-sm font-medium text-text-muted mb-2">Default Backend</label>
        <select
          value={settings.default_backend}
          onChange={(e) => setSettings({ ...settings, default_backend: e.target.value })}
          className="bg-surface-raised border border-border-subtle rounded px-3 py-1.5 text-sm text-text"
        >
          {backends.map((b) => (
            <option key={b.name} value={b.name}>{b.display_name}</option>
          ))}
        </select>
      </div>

      {/* Stage × Phase grid */}
      <div>
        <h2 className="text-sm font-medium text-text-muted mb-3">Per-Stage Configuration</h2>
        <ModelGrid settings={settings} backends={backends} onChange={setSettings} />
      </div>
    </div>
  );
}
