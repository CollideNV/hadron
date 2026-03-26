import { useCallback, useState } from "react";
import type { BackendTemplate, PhaseModel, StageConfig } from "../../api/types";

const STAGE_PHASES: Record<string, { label: string; explore: boolean; plan: boolean }> = {
  intake:                          { label: "Intake",                  explore: false, plan: false },
  behaviour_translation:           { label: "Behaviour Translation",   explore: false, plan: false },
  behaviour_verification:          { label: "Behaviour Verification",  explore: false, plan: false },
  implementation:                  { label: "Implementation",          explore: true,  plan: true  },
  "review:security_reviewer":      { label: "Review: Security",        explore: false, plan: false },
  "review:quality_reviewer":       { label: "Review: Quality",         explore: false, plan: false },
  "review:spec_compliance_reviewer": { label: "Review: Spec Compliance", explore: false, plan: false },
  rework:                          { label: "Rework",                  explore: false, plan: false },
  rebase:                          { label: "Rebase",                  explore: false, plan: false },
};

const BUILTIN_SLUGS = new Set(["anthropic", "openai", "gemini"]);

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

interface Props {
  templates: BackendTemplate[];
  onChange: (templates: BackendTemplate[]) => void;
  defaultSlug: string;
  onDefaultChange: (slug: string) => void;
}

function ModelSelect({
  value,
  models,
  onChange,
}: {
  value: string;
  models: string[];
  onChange: (model: string) => void;
}) {
  if (models.length > 0) {
    return (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-surface-raised border border-border-subtle rounded px-2 py-1 text-xs text-text min-w-[180px]"
      >
        {models.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
    );
  }
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="model ID"
      className="bg-surface-raised border border-border-subtle rounded px-2 py-1 text-xs text-text min-w-[180px]"
    />
  );
}

function StageGrid({
  template,
  onChange,
}: {
  template: BackendTemplate;
  onChange: (stages: Record<string, StageConfig>) => void;
}) {
  const models = template.available_models ?? [];

  const updatePhase = (stage: string, phase: "act" | "explore" | "plan", model: string) => {
    const current = template.stages[stage] ?? {
      act: { backend: template.backend, model: models[0] ?? "" },
      explore: null,
      plan: null,
    };
    const updated: StageConfig = {
      ...current,
      [phase]: { backend: template.backend, model } as PhaseModel,
    };
    onChange({ ...template.stages, [stage]: updated });
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="template-stage-grid">
        <thead>
          <tr className="border-b border-border-subtle">
            <th className="text-left py-2 pr-4 text-text-muted font-medium text-xs uppercase tracking-wide w-48">Stage</th>
            <th className="text-left py-2 px-4 text-text-muted font-medium text-xs uppercase tracking-wide">Explore</th>
            <th className="text-left py-2 px-4 text-text-muted font-medium text-xs uppercase tracking-wide">Plan</th>
            <th className="text-left py-2 px-4 text-text-muted font-medium text-xs uppercase tracking-wide">Act</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(STAGE_PHASES).map(([stage, meta]) => {
            const cfg = template.stages[stage];
            return (
              <tr key={stage} className="border-b border-border-subtle/50">
                <td className="py-3 pr-4 font-medium text-text">{meta.label}</td>
                <td className="py-3 px-4">
                  {meta.explore && cfg?.explore ? (
                    <ModelSelect
                      value={cfg.explore.model}
                      models={models}
                      onChange={(m) => updatePhase(stage, "explore", m)}
                    />
                  ) : (
                    <span className="text-text-dim text-xs">&mdash;</span>
                  )}
                </td>
                <td className="py-3 px-4">
                  {meta.plan && cfg?.plan ? (
                    <ModelSelect
                      value={cfg.plan.model}
                      models={models}
                      onChange={(m) => updatePhase(stage, "plan", m)}
                    />
                  ) : (
                    <span className="text-text-dim text-xs">&mdash;</span>
                  )}
                </td>
                <td className="py-3 px-4">
                  {cfg?.act ? (
                    <ModelSelect
                      value={cfg.act.model}
                      models={models}
                      onChange={(m) => updatePhase(stage, "act", m)}
                    />
                  ) : (
                    <span className="text-text-dim text-xs">&mdash;</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function TemplateEditor({ templates, onChange, defaultSlug, onDefaultChange }: Props) {
  const [activeSlug, setActiveSlug] = useState<string>(templates[0]?.slug ?? "anthropic");
  const activeTemplate = templates.find((t) => t.slug === activeSlug);

  const updateTemplate = useCallback(
    (slug: string, patch: Partial<BackendTemplate>) => {
      onChange(templates.map((t) => (t.slug === slug ? { ...t, ...patch } : t)));
    },
    [templates, onChange],
  );

  const deleteTemplate = useCallback(
    (slug: string) => {
      onChange(templates.filter((t) => t.slug !== slug));
      if (activeSlug === slug) {
        setActiveSlug(templates[0]?.slug ?? "anthropic");
      }
    },
    [templates, onChange, activeSlug],
  );

  const addOpenCodeTemplate = useCallback(() => {
    const newSlug = `opencode-${Date.now()}`;
    const emptyStages: Record<string, StageConfig> = {};
    for (const stage of Object.keys(STAGE_PHASES)) {
      const meta = STAGE_PHASES[stage];
      emptyStages[stage] = {
        act: { backend: "opencode", model: "" },
        explore: meta.explore ? { backend: "opencode", model: "" } : null,
        plan: meta.plan ? { backend: "opencode", model: "" } : null,
      };
    }
    const newTemplate: BackendTemplate = {
      slug: newSlug,
      display_name: "New OpenCode",
      backend: "opencode",
      stages: emptyStages,
      base_url: "",
      available_models: [],
      is_default: false,
    };
    onChange([...templates, newTemplate]);
    setActiveSlug(newSlug);
  }, [templates, onChange]);

  return (
    <div data-testid="template-editor">
      {/* Template tabs */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {templates.map((t) => (
          <button
            key={t.slug}
            data-testid={`template-tab-${t.slug}`}
            onClick={() => setActiveSlug(t.slug)}
            className={`px-3 py-1.5 text-sm rounded-md border transition-colors cursor-pointer ${
              activeSlug === t.slug
                ? "border-accent text-accent bg-accent/10"
                : "border-border-subtle text-text-muted hover:text-text bg-transparent"
            }`}
          >
            {t.display_name}
            {t.slug === defaultSlug && (
              <span className="ml-1.5 text-[10px] bg-accent/20 text-accent px-1.5 py-0.5 rounded" data-testid="default-badge">
                default
              </span>
            )}
          </button>
        ))}
        <button
          data-testid="add-opencode-template"
          onClick={addOpenCodeTemplate}
          className="px-3 py-1.5 text-sm rounded-md border border-dashed border-border-subtle text-text-dim hover:text-text transition-colors cursor-pointer bg-transparent"
        >
          + OpenCode
        </button>
      </div>

      {/* Active template detail */}
      {activeTemplate && (
        <div className="space-y-4">
          {/* Header row with actions */}
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-text">
              {activeTemplate.display_name}
              <span className="ml-2 text-xs text-text-dim">({activeTemplate.backend})</span>
            </h3>
            <div className="flex items-center gap-2">
              {activeTemplate.slug !== defaultSlug && (
                <button
                  data-testid="set-default-btn"
                  onClick={() => onDefaultChange(activeTemplate.slug)}
                  className="px-3 py-1 text-xs rounded-md border border-border-subtle text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer bg-transparent"
                >
                  Set as Default
                </button>
              )}
              {!BUILTIN_SLUGS.has(activeTemplate.slug) && (
                <button
                  data-testid="delete-template-btn"
                  onClick={() => deleteTemplate(activeTemplate.slug)}
                  className="px-3 py-1 text-xs rounded-md text-red-400 hover:text-red-300 transition-colors cursor-pointer bg-transparent border border-red-400/30 hover:border-red-300/30"
                >
                  Delete
                </button>
              )}
            </div>
          </div>

          {/* OpenCode-specific fields */}
          {!BUILTIN_SLUGS.has(activeTemplate.slug) && (
            <div className="p-3 rounded-lg bg-surface-raised border border-border-subtle space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-text-dim mb-1">Display Name</label>
                  <input
                    type="text"
                    data-testid="opencode-display-name"
                    value={activeTemplate.display_name}
                    onChange={(e) => {
                      const display_name = e.target.value;
                      const slug = `opencode-${slugify(display_name)}`;
                      updateTemplate(activeTemplate.slug, { display_name, slug });
                      setActiveSlug(slug);
                    }}
                    placeholder="Local Ollama"
                    className="w-full bg-bg border border-border-subtle rounded px-2 py-1 text-sm text-text"
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-dim mb-1">Base URL</label>
                  <input
                    type="text"
                    data-testid="opencode-base-url"
                    value={activeTemplate.base_url ?? ""}
                    onChange={(e) => updateTemplate(activeTemplate.slug, { base_url: e.target.value })}
                    placeholder="http://localhost:11434/v1"
                    className="w-full bg-bg border border-border-subtle rounded px-2 py-1 text-sm text-text"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-text-dim mb-1">Available Models (comma-separated)</label>
                <input
                  type="text"
                  data-testid="opencode-models"
                  value={(activeTemplate.available_models ?? []).join(", ")}
                  onChange={(e) =>
                    updateTemplate(activeTemplate.slug, {
                      available_models: e.target.value
                        .split(",")
                        .map((m) => m.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="qwen3:7b, llama3.2"
                  className="w-full bg-bg border border-border-subtle rounded px-2 py-1 text-sm text-text"
                />
              </div>
            </div>
          )}

          {/* Stage model grid */}
          <StageGrid
            template={activeTemplate}
            onChange={(stages) => updateTemplate(activeTemplate.slug, { stages })}
          />
        </div>
      )}
    </div>
  );
}
