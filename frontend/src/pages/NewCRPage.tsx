import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { triggerPipeline } from "../api/client";
import type { RawChangeRequest } from "../api/types";
import CRForm from "../components/cr/CRForm";

export default function NewCRPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (cr: RawChangeRequest) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await triggerPipeline(cr);
      navigate(`/cr/${result.cr_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to trigger pipeline");
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto py-8 px-4">
      <h1 className="text-lg font-semibold text-text mb-6">
        New Change Request
      </h1>

      {error && (
        <div className="bg-status-failed/10 text-status-failed px-4 py-3 rounded-lg text-sm mb-4 border border-status-failed/20">
          {error}
        </div>
      )}

      <div className="bg-bg-surface rounded-xl border border-border-subtle p-6">
        <CRForm onSubmit={handleSubmit} submitting={submitting} />
      </div>
    </div>
  );
}
