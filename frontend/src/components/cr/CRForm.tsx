import { useState } from "react";
import type { BackendTemplate, RawChangeRequest } from "../../api/types";
import { BTN_ACCENT, BTN_GHOST } from "../../utils/styles";

interface CRFormProps {
  onSubmit: (cr: RawChangeRequest) => void;
  submitting: boolean;
  onCancel?: () => void;
  templates?: BackendTemplate[];
  defaultTemplateSlug?: string;
}

const inputClass =
  "w-full px-3 py-2 bg-bg border border-border rounded-lg text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/40 placeholder:text-text-dim";

const URL_PATTERN = /^https?:\/\/.+/;

export default function CRForm({ onSubmit, submitting, onCancel, templates, defaultTemplateSlug }: CRFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [urlError, setUrlError] = useState("");
  const [templateSlug, setTemplateSlug] = useState(defaultTemplateSlug ?? "");

  const validateUrl = (url: string) => {
    if (url === "" || URL_PATTERN.test(url)) {
      setUrlError("");
    } else {
      setUrlError("URL must start with http:// or https://");
    }
  };

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setRepoUrl(val);
    validateUrl(val);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (urlError) return;
    onSubmit({
      title,
      description,
      repo_urls: repoUrl ? [repoUrl] : undefined,
      repo_default_branch: branch,
      template_slug: templateSlug || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {templates && templates.length > 0 && (
        <div>
          <label htmlFor="cr-template" className="block text-xs font-medium text-text-muted mb-1.5">
            Backend Template
          </label>
          <select
            id="cr-template"
            data-testid="cr-template-select"
            value={templateSlug}
            onChange={(e) => setTemplateSlug(e.target.value)}
            className={inputClass}
          >
            {templates.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.display_name}{t.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      <div>
        <label htmlFor="cr-title" className="block text-xs font-medium text-text-muted mb-1.5">
          Title
        </label>
        <input
          id="cr-title"
          type="text"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add health check endpoint"
          className={inputClass}
        />
      </div>
      <div>
        <label htmlFor="cr-description" className="block text-xs font-medium text-text-muted mb-1.5">
          Description
        </label>
        <textarea
          id="cr-description"
          required
          rows={5}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the change request in detail..."
          className={`${inputClass} resize-y`}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="cr-repo-url" className="block text-xs font-medium text-text-muted mb-1.5">
            Repository URL
          </label>
          <input
            id="cr-repo-url"
            type="text"
            value={repoUrl}
            onChange={handleUrlChange}
            placeholder="https://github.com/org/repo.git"
            className={`${inputClass}${urlError ? " border-status-failed focus:ring-status-failed/30" : ""}`}
          />
          {urlError && (
            <p className="text-[10px] text-status-failed mt-1">{urlError}</p>
          )}
        </div>
        <div>
          <label htmlFor="cr-branch" className="block text-xs font-medium text-text-muted mb-1.5">
            Default Branch
          </label>
          <input
            id="cr-branch"
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            className={inputClass}
          />
        </div>
      </div>
      <div className="flex gap-3 justify-end">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className={BTN_GHOST}
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          disabled={submitting || !title || !description || !!urlError}
          className={`${BTN_ACCENT} disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          {submitting ? "Submitting..." : "Trigger Pipeline"}
        </button>
      </div>
    </form>
  );
}
