import { useState } from "react";
import type { StageInfo } from "../../utils/buildStageInfos";
import { STAGE_GROUP, GROUP_ACCENT } from "../../utils/stages";
import StageRowHeader from "./StageRowHeader";
import StageRowDetail from "./StageRowDetail";

export default function StageRow({
  info,
  currentStage,
  status,
  onSelect,
}: {
  info: StageInfo;
  currentStage: string;
  status: string;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const group = STAGE_GROUP[info.stage] || "Ship";
  const color = GROUP_ACCENT[group] || "#37e284";
  const isCurrent = info.stage === currentStage;
  const isFailed = isCurrent && status === "failed";
  const isPaused = isCurrent && status === "paused";
  const isCompleted = info.completedAt !== null;

  return (
    <div className="animate-fade-in">
      <StageRowHeader
        info={info}
        isCurrent={isCurrent}
        isFailed={isFailed}
        isPaused={isPaused}
        isCompleted={isCompleted}
        expanded={expanded}
        color={color}
        onToggle={() => setExpanded(!expanded)}
      />
      {expanded && (
        <StageRowDetail info={info} color={color} onSelect={onSelect} />
      )}
    </div>
  );
}
