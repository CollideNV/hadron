import { useState } from "react";
import { sendIntervention } from "../../api/client";

interface InterventionModalProps {
  crId: string;
}

export default function InterventionModal({ crId }: InterventionModalProps) {
  const [open, setOpen] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSend = async () => {
    if (!instructions.trim()) return;
    setSending(true);
    try {
      await sendIntervention(crId, instructions);
      setSent(true);
      setInstructions("");
      setTimeout(() => {
        setOpen(false);
        setSent(false);
      }, 1500);
    } catch {
      // keep modal open on error
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="px-3 py-1.5 bg-bg-card hover:bg-bg-card-hover border border-border-subtle text-text-muted text-xs rounded-md transition-colors cursor-pointer"
      >
        Intervene
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-bg-surface rounded-xl border border-border-subtle shadow-2xl w-full max-w-lg mx-4 p-6">
            <h2 className="text-lg font-semibold text-text mb-4">
              Send Intervention
            </h2>
            <p className="text-sm text-text-muted mb-3">
              Provide instructions for the pipeline agents. This will be
              injected into the next agent prompt.
            </p>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={5}
              placeholder="e.g., Focus on error handling for the /health endpoint..."
              className="w-full px-3 py-2 bg-bg border border-border rounded-lg text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent/50 resize-y placeholder:text-text-dim"
              autoFocus
            />
            <div className="flex items-center justify-end gap-3 mt-4">
              <button
                onClick={() => setOpen(false)}
                className="px-4 py-2 text-sm text-text-muted hover:text-text cursor-pointer bg-transparent border-none transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={sending || !instructions.trim()}
                className="px-4 py-2 bg-accent text-bg rounded-lg text-sm font-medium hover:brightness-110 transition-all disabled:opacity-40 cursor-pointer border-none"
              >
                {sent ? "Sent!" : sending ? "Sending..." : "Send"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
