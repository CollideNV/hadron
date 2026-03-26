import { useCallback, useEffect, useState } from "react";
import type { BackendTemplate, PipelineDefaults } from "../api/types";
import { getDefaultTemplate, getPipelineDefaults, getTemplates, setDefaultTemplate, updatePipelineDefaults, updateTemplates } from "../api/client";
import ApiKeyEditor from "../components/settings/ApiKeyEditor";
import TemplateEditor from "../components/settings/TemplateEditor";
import PipelineDefaultsEditor from "../components/settings/PipelineDefaultsEditor";

export default function SettingsPage() {
  const [templates, setTemplates] = useState<BackendTemplate[]>([]);
  const [savedTemplates, setSavedTemplates] = useState<BackendTemplate[]>([]);
  const [defaultSlug, setDefaultSlug] = useState("anthropic");
  const [savedDefaultSlug, setSavedDefaultSlug] = useState("anthropic");
  const [defaults, setDefaults] = useState<PipelineDefaults | null>(null);
  const [savedDefaults, setSavedDefaults] = useState<PipelineDefaults | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([getTemplates(), getDefaultTemplate(), getPipelineDefaults()])
      .then(([t, dt, d]) => {
        setTemplates(t);
        setSavedTemplates(t);
        setDefaultSlug(dt.slug);
        setSavedDefaultSlug(dt.slug);
        setDefaults(d);
        setSavedDefaults(d);
        setLoaded(true);
      })
      .catch((e) => setError(e.message));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const saves: Promise<unknown>[] = [updateTemplates(templates)];
      if (defaultSlug !== savedDefaultSlug) {
        saves.push(setDefaultTemplate(defaultSlug));
      }
      if (defaults) saves.push(updatePipelineDefaults(defaults));
      const [updatedTemplates] = await Promise.all(saves) as [BackendTemplate[], ...unknown[]];
      setTemplates(updatedTemplates);
      setSavedTemplates(updatedTemplates);
      setSavedDefaultSlug(defaultSlug);
      if (defaults) setSavedDefaults(defaults);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [templates, defaultSlug, savedDefaultSlug, defaults]);

  const handleDiscard = useCallback(() => {
    setTemplates(savedTemplates);
    setDefaultSlug(savedDefaultSlug);
    if (savedDefaults) setDefaults(savedDefaults);
  }, [savedTemplates, savedDefaultSlug, savedDefaults]);

  const dirty =
    JSON.stringify(templates) !== JSON.stringify(savedTemplates) ||
    defaultSlug !== savedDefaultSlug ||
    (defaults !== null && savedDefaults !== null && JSON.stringify(defaults) !== JSON.stringify(savedDefaults));

  if (!loaded) {
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
        <h1 className="text-lg font-semibold text-text">Backend Templates</h1>
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

      {/* Backend Templates */}
      <div className="mb-8">
        <TemplateEditor
          templates={templates}
          onChange={setTemplates}
          defaultSlug={defaultSlug}
          onDefaultChange={setDefaultSlug}
        />
      </div>

      {/* API Keys */}
      <ApiKeyEditor />

      {/* Pipeline Defaults */}
      {defaults && (
        <PipelineDefaultsEditor defaults={defaults} onChange={setDefaults} />
      )}
    </div>
  );
}
