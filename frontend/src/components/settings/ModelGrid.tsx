import type { BackendModels, ModelSettings, PhaseModel, StageConfig } from "../../api/types";

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

interface Props {
  settings: ModelSettings;
  backends: BackendModels[];
  onChange: (settings: ModelSettings) => void;
}

function PhaseCell({
  phase,
  backends,
  onChange,
}: {
  phase: PhaseModel;
  backends: BackendModels[];
  onChange: (phase: PhaseModel) => void;
}) {
  const selectedBackend = backends.find((b) => b.name === phase.backend);
  const models = selectedBackend?.models ?? [];

  return (
    <div className="flex gap-1.5 items-center">
      <select
        value={phase.backend}
        onChange={(e) => {
          const newBackend = e.target.value;
          const newBackendModels = backends.find((b) => b.name === newBackend)?.models ?? [];
          onChange({
            backend: newBackend,
            model: newBackendModels[0] ?? phase.model,
          });
        }}
        className="bg-surface-raised border border-border-subtle rounded px-2 py-1 text-xs text-text min-w-[90px]"
      >
        {backends.map((b) => (
          <option key={b.name} value={b.name}>{b.display_name}</option>
        ))}
      </select>
      {models.length > 0 ? (
        <select
          value={phase.model}
          onChange={(e) => onChange({ ...phase, model: e.target.value })}
          className="bg-surface-raised border border-border-subtle rounded px-2 py-1 text-xs text-text min-w-[180px]"
        >
          {models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={phase.model}
          onChange={(e) => onChange({ ...phase, model: e.target.value })}
          placeholder="model ID"
          className="bg-surface-raised border border-border-subtle rounded px-2 py-1 text-xs text-text min-w-[180px]"
        />
      )}
    </div>
  );
}

function DisabledCell() {
  return <span className="text-text-dim text-xs">&mdash;</span>;
}

export default function ModelGrid({ settings, backends, onChange }: Props) {
  const updateStage = (stage: string, phase: "act" | "explore" | "plan", value: PhaseModel) => {
    const current = settings.stages[stage] ?? { act: { backend: "claude", model: "claude-sonnet-4-6" }, explore: null, plan: null };
    const updated: StageConfig = { ...current, [phase]: value };
    onChange({
      ...settings,
      stages: { ...settings.stages, [stage]: updated },
    });
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
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
            const cfg = settings.stages[stage];
            return (
              <tr key={stage} className="border-b border-border-subtle/50">
                <td className="py-3 pr-4 font-medium text-text">{meta.label}</td>
                <td className="py-3 px-4">
                  {meta.explore && cfg?.explore ? (
                    <PhaseCell phase={cfg.explore} backends={backends} onChange={(v) => updateStage(stage, "explore", v)} />
                  ) : (
                    <DisabledCell />
                  )}
                </td>
                <td className="py-3 px-4">
                  {meta.plan && cfg?.plan ? (
                    <PhaseCell phase={cfg.plan} backends={backends} onChange={(v) => updateStage(stage, "plan", v)} />
                  ) : (
                    <DisabledCell />
                  )}
                </td>
                <td className="py-3 px-4">
                  {cfg?.act ? (
                    <PhaseCell phase={cfg.act} backends={backends} onChange={(v) => updateStage(stage, "act", v)} />
                  ) : (
                    <DisabledCell />
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
