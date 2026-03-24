import { useState } from "react";
import { formatCost } from "../../utils/format";
import type { PipelineEvent } from "../../api/types";
import { useCostBreakdown } from "../../hooks/useCostBreakdown";
import CostDashboard from "./CostDashboard";
import Modal from "../shared/Modal";

interface CostTrackerProps {
  costUsd: number;
  events?: PipelineEvent[];
}

export default function CostTracker({ costUsd, events = [] }: CostTrackerProps) {
  const [open, setOpen] = useState(false);
  const breakdown = useCostBreakdown(events);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        data-testid="cost-tracker"
        className="flex items-center gap-1.5 bg-bg-card rounded-md px-2.5 py-1 border border-border-subtle cursor-pointer hover:border-accent/30 transition-colors"
      >
        <span className="text-[10px] text-text-dim uppercase tracking-wider">
          Cost
        </span>
        <span className="font-mono text-sm text-accent font-medium">
          {formatCost(costUsd)}
        </span>
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Cost Breakdown" wide>
        <CostDashboard breakdown={breakdown} />
      </Modal>
    </>
  );
}
