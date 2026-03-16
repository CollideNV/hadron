import { useCallback, useEffect, useState } from "react";
import type { PromptTemplate, PromptTemplateDetail } from "../api/types";
import { getPrompt, listPrompts, updatePrompt } from "../api/client";
import PromptEditor from "../components/prompts/PromptEditor";

function humanize(role: string): string {
  return role
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function PromptsPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PromptTemplateDetail | null>(null);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPrompts().then(setTemplates).catch((e) => setError(e.message));
  }, []);

  const loadPrompt = useCallback(async (role: string) => {
    setSelected(role);
    setError(null);
    try {
      const d = await getPrompt(role);
      setDetail(d);
      setEditContent(d.content);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updatePrompt(selected, editContent);
      setDetail(updated);
      setEditContent(updated.content);
      setTemplates((prev) =>
        prev.map((t) =>
          t.role === selected
            ? { ...t, version: updated.version, updated_at: updated.updated_at }
            : t,
        ),
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [selected, editContent]);

  const handleDiscard = useCallback(() => {
    if (detail) setEditContent(detail.content);
  }, [detail]);

  const dirty = detail !== null && editContent !== detail.content;

  return (
    <div className="flex h-[calc(100vh-57px)]">
      {/* Sidebar */}
      <aside className="w-72 border-r border-border-subtle overflow-y-auto p-4 flex-shrink-0">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-4">
          Prompt Templates
        </h2>
        <ul className="space-y-1">
          {templates.map((t) => (
            <li key={t.role}>
              <button
                onClick={() => loadPrompt(t.role)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors cursor-pointer border-none ${
                  selected === t.role
                    ? "bg-accent-dim text-accent"
                    : "text-text hover:bg-surface-raised bg-transparent"
                }`}
              >
                <div className="font-medium">{humanize(t.role)}</div>
                <div className="text-xs text-text-dim mt-0.5 flex items-center gap-2">
                  <span>{t.description}</span>
                  <span className="ml-auto text-[10px] bg-surface-raised px-1.5 py-0.5 rounded">
                    v{t.version}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* Editor panel */}
      <section className="flex-1 p-6 flex flex-col min-w-0">
        {error && (
          <div className="mb-4 px-4 py-2 bg-red-500/10 text-red-400 rounded-lg text-sm">
            {error}
          </div>
        )}
        {detail ? (
          <>
            <div className="mb-4">
              <h1 className="text-lg font-semibold text-text">
                {humanize(detail.role)}
              </h1>
              <p className="text-sm text-text-dim">{detail.description}</p>
            </div>
            <div className="flex-1 min-h-0">
              <PromptEditor
                content={editContent}
                onChange={setEditContent}
                onSave={handleSave}
                onDiscard={handleDiscard}
                dirty={dirty}
                saving={saving}
              />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-text-dim text-sm">
            Select a prompt template to edit
          </div>
        )}
      </section>
    </div>
  );
}
