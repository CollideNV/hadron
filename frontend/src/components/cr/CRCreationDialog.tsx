import { useState, useEffect } from "react";
import Modal from "../shared/Modal";
import CRForm from "./CRForm";
import { getTemplates, triggerPipeline } from "../../api/client";
import type { BackendTemplate, RawChangeRequest } from "../../api/types";

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
  const [templates, setTemplates] = useState<BackendTemplate[]>([]);
  const [templatesLoaded, setTemplatesLoaded] = useState(false);

  // Reset state and load templates whenever the dialog opens
  useEffect(() => {
    if (open) {
      setSubmitting(false);
      setError(null);
      setTemplatesLoaded(false);
      getTemplates()
        .then(setTemplates)
        .catch(() => {})
        .finally(() => setTemplatesLoaded(true));
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
      {!templatesLoaded ? (
        <div className="text-text-dim text-sm py-8 text-center">Loading…</div>
      ) : (
      <CRForm
        onSubmit={handleSubmit}
        submitting={submitting}
        onCancel={submitting ? undefined : handleClose}
        templates={templates}
        defaultTemplateSlug={templates.find((t) => t.is_default)?.slug}
      />
      )}
    </Modal>
  );
}
