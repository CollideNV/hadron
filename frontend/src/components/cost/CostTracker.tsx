interface CostTrackerProps {
  costUsd: number;
}

export default function CostTracker({ costUsd }: CostTrackerProps) {
  return (
    <div className="flex items-center gap-1.5 bg-bg-card rounded-md px-2.5 py-1 border border-border-subtle">
      <span className="text-[10px] text-text-dim uppercase tracking-wider">
        Cost
      </span>
      <span className="font-mono text-sm text-accent font-medium">
        ${costUsd.toFixed(4)}
      </span>
    </div>
  );
}
