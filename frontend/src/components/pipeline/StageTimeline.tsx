import { useCallback, useMemo, useRef } from "react";
import { STAGES, type PipelineEvent } from "../../api/types";
import {
  GROUP_COLORS,
  STAGE_META,
  GROUPS,
  FEEDBACK_LOOPS,
  type LoopArc,
} from "./stageTimelineConstants";
import StageNode from "./StageNode";
import ForwardArrow from "./ForwardArrow";
import GroupForwardArrow from "./GroupForwardArrow";
import BackwardLoopOverlay from "./BackwardLoopOverlay";

interface StageTimelineProps {
  currentStage: string;
  completedStages: Set<string>;
  status: string;
  selectedStage?: string | null;
  onSelectStage?: (stage: string) => void;
  events?: PipelineEvent[];
}

export default function StageTimeline({
  currentStage,
  completedStages,
  status,
  selectedStage,
  onSelectStage,
  events = [],
}: StageTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRefsMap = useRef<Map<string, HTMLElement>>(new Map());

  const setStageRef = useCallback((stage: string, el: HTMLElement | null) => {
    if (el) {
      stageRefsMap.current.set(stage, el);
    } else {
      stageRefsMap.current.delete(stage);
    }
  }, []);

  const loopCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const e of events) {
      if (e.event_type === "stage_entered") {
        counts.set(e.stage, (counts.get(e.stage) || 0) + 1);
      }
    }
    return {
      behaviour_translation: Math.max(0, (counts.get("behaviour_translation") || 0) - 1),
      tdd: Math.max(0, (counts.get("tdd") || 0) - 1),
    };
  }, [events]);

  const loopArcs: LoopArc[] = useMemo(
    () =>
      FEEDBACK_LOOPS.map((loop) => ({
        from: loop.from,
        to: loop.to,
        count: loopCounts[loop.countKey],
        label: loop.label,
      })),
    [loopCounts],
  );

  return (
    <div className="px-4 py-3 overflow-x-auto">
      <div className="flex items-end gap-2 relative pb-8" ref={containerRef}>
        {GROUPS.map((group, gi) => {
          const groupStages = STAGES.filter(
            (s) => STAGE_META[s].group === group,
          );
          const color = GROUP_COLORS[group];
          const anyCompleted = groupStages.some((s) =>
            completedStages.has(s),
          );
          const anyCurrent = groupStages.some((s) => s === currentStage);
          const lastStageCompleted = groupStages.every((s) =>
            completedStages.has(s),
          );

          return (
            <div key={group} className="flex items-end gap-2">
              <div className="flex flex-col">
                <span
                  className="text-[9px] uppercase tracking-[0.12em] mb-2 font-medium transition-colors"
                  style={{
                    color: anyCurrent
                      ? color.accent
                      : anyCompleted
                        ? color.dim
                        : "#63717a",
                  }}
                >
                  {group}
                </span>
                <div className="flex items-start gap-0.5">
                  {groupStages.map((stage, i) => {
                    const isCompleted = completedStages.has(stage);
                    const isCurrent = currentStage === stage;
                    const isFailed = isCurrent && status === "failed";
                    const isPaused = isCurrent && status === "paused";
                    const isSelected = selectedStage === stage;

                    return (
                      <div key={stage} className="flex items-start">
                        <div ref={(el) => setStageRef(stage, el)}>
                          <StageNode
                            stage={stage}
                            isCompleted={isCompleted}
                            isCurrent={isCurrent}
                            isFailed={isFailed}
                            isPaused={isPaused}
                            isSelected={isSelected}
                            color={color}
                            onClick={() => onSelectStage?.(stage)}
                          />
                        </div>
                        {i < groupStages.length - 1 && (
                          <ForwardArrow
                            filled={isCompleted}
                            active={isCurrent && !isFailed && !isPaused}
                            color={color}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              {gi < GROUPS.length - 1 && (
                <GroupForwardArrow filled={lastStageCompleted} />
              )}
            </div>
          );
        })}
        <BackwardLoopOverlay
          containerRef={containerRef}
          stageRefs={stageRefsMap}
          loops={loopArcs}
        />
      </div>
    </div>
  );
}
