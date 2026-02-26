import { useState, useEffect } from "react";
import type { RawChangeRequest, ModelConfig } from "../../api/types";
import { listModels } from "../../api/client";

interface CRFormProps {
  onSubmit: (cr: RawChangeRequest) => void;
  submitting: boolean;
}

const inputClass =
  "w-full px-3 py-2 bg-bg border border-border rounded-lg text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/40 placeholder:text-text-dim";

export default function CRForm({ onSubmit, submitting }: CRFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [testCommand, setTestCommand] = useState("pytest");
  const [language, setLanguage] = useState("python");
  const [model, setModel] = useState("default");
  const [models, setModels] = useState<ModelConfig[]>([]);

  useEffect(() => {
    listModels().then(setModels).catch(console.error);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      title,
      description,
      repo_url: repoUrl || undefined,
      repo_default_branch: branch,
      test_command: testCommand,
      language,
      model: model === "default" ? undefined : model,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-xs font-medium text-text-muted mb-1.5">
          Title
        </label>
        <input
          type="text"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add health check endpoint"
          className={inputClass}
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-text-muted mb-1.5">
          Description
        </label>
        <textarea
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
          <label className="block text-xs font-medium text-text-muted mb-1.5">
            Repository URL
          </label>
          <input
            type="text"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="/path/to/repo or https://..."
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1.5">
            Default Branch
          </label>
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            className={inputClass}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1.5">
            Test Command
          </label>
          <input
            type="text"
            value={testCommand}
            onChange={(e) => setTestCommand(e.target.value)}
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1.5">
            Language
          </label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className={inputClass}
          >
            <option value="python">Python</option>
            <option value="typescript">TypeScript</option>
            <option value="javascript">JavaScript</option>
            <option value="go">Go</option>
            <option value="java">Java</option>
            <option value="rust">Rust</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-text-muted mb-1.5">
          Model
        </label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className={inputClass}
        >
          <option value="default">Default (Gemini 3 Pro Preview)</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.provider})
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-text-dim">
          Select the AI model used for all pipeline stages.
        </p>
      </div>

      <button
        type="submit"
        disabled={submitting || !title || !description}
        className="w-full py-2.5 px-4 bg-accent text-bg rounded-lg font-medium text-sm hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer border-none"
      >
        {submitting ? "Submitting..." : "Trigger Pipeline"}
      </button>
    </form>
  );
}
