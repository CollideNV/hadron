import { useCallback } from "react";
import type { OpenCodeEndpoint } from "../../api/types";

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

interface Props {
  endpoints: OpenCodeEndpoint[];
  onChange: (endpoints: OpenCodeEndpoint[]) => void;
}

export default function OpenCodeEndpointEditor({ endpoints, onChange }: Props) {
  const update = useCallback(
    (index: number, patch: Partial<OpenCodeEndpoint>) => {
      const next = endpoints.map((ep, i) => (i === index ? { ...ep, ...patch } : ep));
      onChange(next);
    },
    [endpoints, onChange],
  );

  const remove = useCallback(
    (index: number) => onChange(endpoints.filter((_, i) => i !== index)),
    [endpoints, onChange],
  );

  const add = useCallback(() => {
    onChange([...endpoints, { slug: "", display_name: "", base_url: "", models: [] }]);
  }, [endpoints, onChange]);

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-text-muted">OpenCode Endpoints</h2>
        <button
          onClick={add}
          className="px-3 py-1 text-xs rounded-md border border-border-subtle text-text-muted hover:text-text transition-colors cursor-pointer bg-transparent"
        >
          + Add Endpoint
        </button>
      </div>
      {endpoints.length === 0 && (
        <p className="text-xs text-text-dim">
          No named endpoints. Add one to use a custom OpenAI-compatible server as a backend.
        </p>
      )}
      <div className="space-y-3">
        {endpoints.map((ep, i) => (
          <div key={i} className="p-3 rounded-lg bg-surface-raised border border-border-subtle">
            <div className="grid grid-cols-[1fr_1fr_auto] gap-3 mb-2">
              <div>
                <label className="block text-xs text-text-dim mb-1">Display Name</label>
                <input
                  type="text"
                  value={ep.display_name}
                  onChange={(e) => {
                    const display_name = e.target.value;
                    const slug = slugify(display_name);
                    update(i, { display_name, slug });
                  }}
                  placeholder="Local Ollama"
                  className="w-full bg-bg border border-border-subtle rounded px-2 py-1 text-sm text-text"
                />
                {ep.slug && (
                  <span className="text-[10px] text-text-dim mt-0.5 block">
                    opencode:{ep.slug}
                  </span>
                )}
              </div>
              <div>
                <label className="block text-xs text-text-dim mb-1">Base URL</label>
                <input
                  type="text"
                  value={ep.base_url}
                  onChange={(e) => update(i, { base_url: e.target.value })}
                  placeholder="http://localhost:11434/v1"
                  className="w-full bg-bg border border-border-subtle rounded px-2 py-1 text-sm text-text"
                />
              </div>
              <div className="flex items-end">
                <button
                  onClick={() => remove(i)}
                  className="px-2 py-1 text-xs text-red-400 hover:text-red-300 transition-colors cursor-pointer bg-transparent border-none"
                >
                  Remove
                </button>
              </div>
            </div>
            <div>
              <label className="block text-xs text-text-dim mb-1">Models (comma-separated)</label>
              <input
                type="text"
                value={ep.models.join(", ")}
                onChange={(e) =>
                  update(i, {
                    models: e.target.value
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
        ))}
      </div>
    </div>
  );
}
