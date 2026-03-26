import type { PipelineDefaults } from "../../api/types";

interface PipelineDefaultsEditorProps {
  defaults: PipelineDefaults;
  onChange: (defaults: PipelineDefaults) => void;
}

const DELIVERY_STRATEGIES = [
  { value: "self_contained", label: "Self-contained" },
  { value: "push_and_wait", label: "Push & Wait" },
  { value: "push_and_forget", label: "Push & Forget" },
];

const INPUT = "bg-surface-raised border border-border-subtle rounded px-3 py-1.5 text-sm text-text w-full";
const LABEL = "block text-xs font-medium text-text-muted mb-1";

export default function PipelineDefaultsEditor({ defaults, onChange }: PipelineDefaultsEditorProps) {
  const set = <K extends keyof PipelineDefaults>(key: K, value: PipelineDefaults[K]) =>
    onChange({ ...defaults, [key]: value });

  return (
    <div className="mb-8">
      <h2 className="text-sm font-medium text-text-muted mb-3">Pipeline Defaults</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {/* Circuit breakers */}
        <div>
          <label className={LABEL}>Max Verification Loops</label>
          <input
            type="number"
            min={1}
            max={10}
            value={defaults.max_verification_loops}
            onChange={(e) => set("max_verification_loops", Number(e.target.value))}
            className={INPUT}
            data-testid="defaults-max-verification-loops"
          />
        </div>
        <div>
          <label className={LABEL}>Max Review/Dev Loops</label>
          <input
            type="number"
            min={1}
            max={10}
            value={defaults.max_review_dev_loops}
            onChange={(e) => set("max_review_dev_loops", Number(e.target.value))}
            className={INPUT}
            data-testid="defaults-max-review-dev-loops"
          />
        </div>
        <div>
          <label className={LABEL}>Max Cost (USD)</label>
          <input
            type="number"
            min={0.01}
            step={0.5}
            value={defaults.max_cost_usd}
            onChange={(e) => set("max_cost_usd", Number(e.target.value))}
            className={INPUT}
            data-testid="defaults-max-cost-usd"
          />
        </div>

        {/* Timeouts */}
        <div>
          <label className={LABEL}>Agent Timeout (s)</label>
          <input
            type="number"
            min={30}
            step={30}
            value={defaults.agent_timeout}
            onChange={(e) => set("agent_timeout", Number(e.target.value))}
            className={INPUT}
            data-testid="defaults-agent-timeout"
          />
        </div>
        <div>
          <label className={LABEL}>Test Timeout (s)</label>
          <input
            type="number"
            min={10}
            step={10}
            value={defaults.test_timeout}
            onChange={(e) => set("test_timeout", Number(e.target.value))}
            className={INPUT}
            data-testid="defaults-test-timeout"
          />
        </div>

        {/* Delivery strategy */}
        <div>
          <label className={LABEL}>Delivery Strategy</label>
          <select
            value={defaults.delivery_strategy}
            onChange={(e) => set("delivery_strategy", e.target.value)}
            className={INPUT}
            data-testid="defaults-delivery-strategy"
          >
            {DELIVERY_STRATEGIES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
