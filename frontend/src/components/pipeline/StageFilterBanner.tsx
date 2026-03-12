interface StageFilterBannerProps {
  selectedStage: string;
  onClear: () => void;
}

export default function StageFilterBanner({ selectedStage, onClear }: StageFilterBannerProps) {
  return (
    <div className="bg-bg-card border-b border-border-subtle px-4 py-1.5 flex items-center gap-2">
      <span className="text-[10px] text-text-dim uppercase tracking-wider">
        Stage
      </span>
      <span className="text-xs text-accent font-medium">
        {selectedStage.replace(/_/g, " ")}
      </span>
      <button
        onClick={onClear}
        className="text-[10px] text-text-dim hover:text-text ml-auto cursor-pointer bg-transparent border-none transition-colors"
      >
        Close
      </button>
    </div>
  );
}
