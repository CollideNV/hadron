import { useCallback, useEffect, useState } from "react";
import type { BackendModels, ModelSettings, OpenCodeEndpoint, PipelineDefaults } from "../api/types";
import { getAvailableBackends, getModelSettings, getOpenCodeEndpoints, getPipelineDefaults, updateModelSettings, updateOpenCodeEndpoints, updatePipelineDefaults } from "../api/client";
import ModelGrid from "../components/settings/ModelGrid";
import OpenCodeEndpointEditor from "../components/settings/OpenCodeEndpointEditor";
import PipelineDefaultsEditor from "../components/settings/PipelineDefaultsEditor";

export default function SettingsPage() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [savedSettings, setSavedSettings] = useState<ModelSettings | null>(null);
  const [backends, setBackends] = useState<BackendModels[]>([]);
  const [endpoints, setEndpoints] = useState<OpenCodeEndpoint[]>([]);
  const [savedEndpoints, setSavedEndpoints] = useState<OpenCodeEndpoint[]>([]);
  const [defaults, setDefaults] = useState<PipelineDefaults | null>(null);
  const [savedDefaults, setSavedDefaults] = useState<PipelineDefaults | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getModelSettings(), getAvailableBackends(), getOpenCodeEndpoints(), getPipelineDefaults()])
      .then(([s, b, ep, d]) => {
        setSettings(s);
        setSavedSettings(s);
        setBackends(b);
        setEndpoints(ep);
        setSavedEndpoints(ep);
        setDefaults(d);
        setSavedDefaults(d);
      })
      .catch((e) => setError(e.message));
  }, []);

  const handleSave = useCallback(async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const saves: Promise<unknown>[] = [
        updateModelSettings(settings),
        updateOpenCodeEndpoints(endpoints),
      ];
      if (defaults) saves.push(updatePipelineDefaults(defaults));
      const [updated] = await Promise.all(saves) as [ModelSettings, ...unknown[]];
      setSettings(updated);
      setSavedSettings(updated);
      setSavedEndpoints(endpoints);
      if (defaults) setSavedDefaults(defaults);
      // Re-fetch backends so new endpoints appear in dropdowns
      const b = await getAvailableBackends();
      setBackends(b);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [settings, endpoints, defaults]);

  const handleDiscard = useCallback(() => {
    if (savedSettings) setSettings(savedSettings);
    setEndpoints(savedEndpoints);
    if (savedDefaults) setDefaults(savedDefaults);
  }, [savedSettings, savedEndpoints, savedDefaults]);

  const dirty =
    (settings !== null && savedSettings !== null && JSON.stringify(settings) !== JSON.stringify(savedSettings)) ||
    JSON.stringify(endpoints) !== JSON.stringify(savedEndpoints) ||
    (defaults !== null && savedDefaults !== null && JSON.stringify(defaults) !== JSON.stringify(savedDefaults));

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

      {/* Pipeline Defaults */}
      {defaults && (
        <PipelineDefaultsEditor defaults={defaults} onChange={setDefaults} />
      )}

      {/* OpenCode Endpoints */}
      <OpenCodeEndpointEditor endpoints={endpoints} onChange={setEndpoints} />

      {/* Stage × Phase grid */}
      <div>
        <h2 className="text-sm font-medium text-text-muted mb-3">Per-Stage Configuration</h2>
        <ModelGrid settings={settings} backends={backends} onChange={setSettings} />
      </div>
    </div>
  );
}
