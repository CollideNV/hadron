import { useMemo } from "react";
import type { PipelineEvent } from "../../api/types";
import { buildStageInfos } from "../../utils/buildStageInfos";
import StageRow from "./StageRow";

interface EventLogProps {
  events: PipelineEvent[];
  currentStage?: string;
  status?: string;
  onSelectStage?: (stage: string) => void;
}

export default function EventLog({
  events,
  currentStage = "",
  status = "",
  onSelectStage,
}: EventLogProps) {
  const stages = useMemo(() => buildStageInfos(events), [events]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-subtle">
        <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          Pipeline Stages
        </h3>
        <span className="text-[10px] text-text-dim">
          {stages.length} stage{stages.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {stages.length === 0 && (
          <p className="text-xs text-text-dim py-8 text-center">
            Waiting for events...
          </p>
        )}
        {stages.map((info) => (
          <StageRow
            key={info.stage}
            info={info}
            currentStage={currentStage}
            status={status}
            onSelect={() => onSelectStage?.(info.stage)}
          />
        ))}
      </div>
    </div>
  );
}
