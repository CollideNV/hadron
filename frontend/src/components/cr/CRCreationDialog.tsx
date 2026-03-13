import { useState, useEffect } from "react";
import Modal from "../shared/Modal";
import CRForm from "./CRForm";
import { triggerPipeline } from "../../api/client";
import type { RawChangeRequest } from "../../api/types";

interface CRCreationDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (crId: string) => void;
}

export default function CRCreationDialog({
  open,
  onClose,
  onCreated,
}: CRCreationDialogProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state whenever the dialog opens
  useEffect(() => {
    if (open) {
      setSubmitting(false);
      setError(null);
    }
  }, [open]);

  const handleSubmit = async (cr: RawChangeRequest) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await triggerPipeline(cr);
      onCreated(result.cr_id);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to trigger pipeline");
      setSubmitting(false);
    }
  };

  // Prevent closing while a submission is in flight
  const handleClose = () => {
    if (!submitting) {
      onClose();
    }
  };

  return (
    <Modal open={open} onClose={handleClose} title="Create Change Request">
      {error && (
        <div
          role="alert"
          className="bg-red-900/20 text-red-400 border border-red-800 rounded-lg px-4 py-3 text-sm mb-4"
        >
          {error}
        </div>
      )}
      <CRForm
        onSubmit={handleSubmit}
        submitting={submitting}
        onCancel={submitting ? undefined : handleClose}
      />
    </Modal>
  );
}
