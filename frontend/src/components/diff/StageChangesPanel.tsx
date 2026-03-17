import type { PipelineEvent, StageDiffData, StageDiffFile } from "../../api/types";
import UnifiedDiffView from "./UnifiedDiffView";
import FeatureFileView from "./FeatureFileView";

interface Props {
  stageName: string;
  stageDiffs: PipelineEvent[];
}

export default function StageChangesPanel({ stageName, stageDiffs }: Props) {
  if (stageDiffs.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-xs text-text-dim">(no changes captured)</p>
      </div>
    );
  }

  // Use the latest diff event for this stage
  const latest = stageDiffs[stageDiffs.length - 1];
  const data = latest.data as StageDiffData;
  const files = (data.files ?? []) as StageDiffFile[];
  const hasDiff = data.diff && data.diff.length > 0;
  const hasFiles = files.length > 0;

  // Determine what to show based on stage
  const showFeatures =
    stageName === "behaviour_translation" ||
    stageName === "behaviour_verification" ||
    (stageName === "review" && hasFiles);

  const showDiff =
    stageName === "implementation" ||
    stageName === "review" ||
    stageName === "delivery" ||
    // Show diff for behaviour stages if there is one
    (showFeatures && hasDiff);

  if (!showDiff && !showFeatures) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-xs text-text-dim">No changes for this stage</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-bg">
      {showFeatures && hasFiles && (
        <div>
          <div className="px-3 py-2 border-b border-border-subtle bg-bg-surface">
            <h4 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
              Feature Specs
            </h4>
          </div>
          <FeatureFileView files={files} truncated={data.files_truncated} />
        </div>
      )}
      {showDiff && hasDiff && (
        <div>
          <div className="px-3 py-2 border-b border-border-subtle bg-bg-surface">
            <h4 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
              Code Diff
            </h4>
          </div>
          <UnifiedDiffView data={data} />
        </div>
      )}
    </div>
  );
}
