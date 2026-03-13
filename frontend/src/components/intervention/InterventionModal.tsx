import { useState } from "react";
import { sendIntervention } from "../../api/client";
import Modal from "../shared/Modal";
import { BTN_ACCENT, BTN_GHOST } from "../../utils/styles";
import { MODAL_SUCCESS_DELAY_MS } from "../../utils/constants";

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
      }, MODAL_SUCCESS_DELAY_MS);
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

      <Modal open={open} onClose={() => setOpen(false)} title="Send Intervention">
        <p className="text-sm text-text-muted mb-3 -mt-2">
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
            className={BTN_GHOST}
          >
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={sending || !instructions.trim()}
            className={BTN_ACCENT}
          >
            {sent ? "Sent!" : sending ? "Sending..." : "Send"}
          </button>
        </div>
      </Modal>
    </>
  );
}
