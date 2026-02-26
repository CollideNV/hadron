import { useState } from "react";
import { resumePipeline } from "../../api/client";

interface ResumeModalProps {
  crId: string;
  status: string;
}

const PRESET_ACTIONS: { label: string; overrides: Record<string, unknown> }[] = [
  { label: "Skip rebase conflicts", overrides: { rebase_clean: true } },
  { label: "Skip code review", overrides: { review_passed: true } },
  { label: "Retry from checkpoint", overrides: {} },
];

export default function ResumeModal({ crId, status }: ResumeModalProps) {
  const [open, setOpen] = useState(false);
  const [customJson, setCustomJson] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  if (status !== "paused" && status !== "failed") return null;

  const handleResume = async (overrides: Record<string, unknown>) => {
    setSending(true);
    setError("");
    try {
      await resumePipeline(crId, overrides);
      setSent(true);
      setCustomJson("");
      setTimeout(() => {
        setOpen(false);
        setSent(false);
      }, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resume failed");
    } finally {
      setSending(false);
    }
  };

  const handleCustomResume = () => {
    try {
      const parsed = customJson.trim() ? JSON.parse(customJson) : {};
      handleResume(parsed);
    } catch {
      setError("Invalid JSON");
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="px-3 py-1.5 bg-accent/20 hover:bg-accent/30 border border-accent/40 text-accent text-xs rounded-md transition-colors cursor-pointer font-medium"
      >
        Resume
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-bg-surface rounded-xl border border-border-subtle shadow-2xl w-full max-w-lg mx-4 p-6">
            <h2 className="text-lg font-semibold text-text mb-1">
              Resume Pipeline
            </h2>
            <p className="text-sm text-text-muted mb-4">
              Choose an action to resume this {status} pipeline.
            </p>

            {/* Preset buttons */}
            <div className="flex flex-col gap-2 mb-4">
              {PRESET_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  onClick={() => handleResume(action.overrides)}
                  disabled={sending}
                  className="w-full px-4 py-2.5 bg-bg-card hover:bg-bg-card-hover border border-border-subtle text-text text-sm rounded-lg transition-colors cursor-pointer text-left disabled:opacity-40"
                >
                  <span className="font-medium">{action.label}</span>
                  {Object.keys(action.overrides).length > 0 && (
                    <span className="text-text-dim ml-2 text-xs font-mono">
                      {JSON.stringify(action.overrides)}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Custom JSON */}
            <details className="mb-4">
              <summary className="text-xs text-text-dim cursor-pointer hover:text-text-muted transition-colors">
                Custom overrides (JSON)
              </summary>
              <textarea
                value={customJson}
                onChange={(e) => setCustomJson(e.target.value)}
                rows={3}
                placeholder='{"rebase_clean": true, "review_passed": true}'
                className="w-full mt-2 px-3 py-2 bg-bg border border-border rounded-lg text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent/50 resize-y placeholder:text-text-dim"
              />
              <button
                onClick={handleCustomResume}
                disabled={sending}
                className="mt-2 px-4 py-2 bg-accent text-bg rounded-lg text-sm font-medium hover:brightness-110 transition-all disabled:opacity-40 cursor-pointer border-none"
              >
                {sent ? "Sent!" : sending ? "Resuming..." : "Resume with custom overrides"}
              </button>
            </details>

            {error && (
              <p className="text-xs text-status-failed mb-3">{error}</p>
            )}

            <div className="flex items-center justify-end">
              <button
                onClick={() => {
                  setOpen(false);
                  setError("");
                }}
                className="px-4 py-2 text-sm text-text-muted hover:text-text cursor-pointer bg-transparent border-none transition-colors"
              >
                Cancel
              </button>
              {sent && (
                <span className="text-sm text-accent font-medium ml-3">
                  Resumed!
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
