import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { STAGES, type PipelineEvent, type Stage } from "../../api/types";

const GROUP_COLORS: Record<string, { accent: string; bg: string; border: string; dim: string }> = {
  Understand: {
    accent: "#4dc9f6",   // cyan
    bg: "rgba(77, 201, 246, 0.12)",
    border: "rgba(77, 201, 246, 0.25)",
    dim: "rgba(77, 201, 246, 0.5)",
  },
  Specify: {
    accent: "#a78bfa",   // violet
    bg: "rgba(167, 139, 250, 0.12)",
    border: "rgba(167, 139, 250, 0.25)",
    dim: "rgba(167, 139, 250, 0.5)",
  },
  Build: {
    accent: "#37e284",   // green (Collide accent)
    bg: "rgba(55, 226, 132, 0.12)",
    border: "rgba(55, 226, 132, 0.25)",
    dim: "rgba(55, 226, 132, 0.5)",
  },
  Validate: {
    accent: "#f0b832",   // amber
    bg: "rgba(240, 184, 50, 0.12)",
    border: "rgba(240, 184, 50, 0.25)",
    dim: "rgba(240, 184, 50, 0.5)",
  },
  Ship: {
    accent: "#f472b6",   // pink
    bg: "rgba(244, 114, 182, 0.12)",
    border: "rgba(244, 114, 182, 0.25)",
    dim: "rgba(244, 114, 182, 0.5)",
  },
};

const STAGE_META: Record<
  Stage,
  { label: string; icon: string; group: string }
> = {
  intake: { label: "Intake", icon: "IN", group: "Understand" },
  repo_id: { label: "Repo ID", icon: "ID", group: "Understand" },
  worktree_setup: { label: "Worktree", icon: "WT", group: "Understand" },
  behaviour_translation: { label: "Translate", icon: "BT", group: "Specify" },
  behaviour_verification: { label: "Verify", icon: "BV", group: "Specify" },
  tdd: { label: "TDD", icon: "TD", group: "Build" },
  review: { label: "Review", icon: "RV", group: "Validate" },
  rebase: { label: "Rebase", icon: "RB", group: "Validate" },
  delivery: { label: "Deliver", icon: "DL", group: "Ship" },
  release_gate: { label: "Gate", icon: "GT", group: "Ship" },
  release: { label: "Release", icon: "RL", group: "Ship" },
  retrospective: { label: "Retro", icon: "RT", group: "Ship" },
};

const GROUPS = ["Understand", "Specify", "Build", "Validate", "Ship"];

const FEEDBACK_LOOPS: {
  from: Stage;
  to: Stage;
  label: string;
  countKey: "behaviour_translation" | "tdd";
}[] = [
  {
    from: "behaviour_verification",
    to: "behaviour_translation",
    label: "spec retry",
    countKey: "behaviour_translation",
  },
  {
    from: "review",
    to: "tdd",
    label: "review retry",
    countKey: "tdd",
  },
];

interface StageTimelineProps {
  currentStage: string;
  completedStages: Set<string>;
  status: string;
  selectedStage?: string | null;
  onSelectStage?: (stage: string) => void;
  events?: PipelineEvent[];
}

function StageNode({
  stage,
  isCompleted,
  isCurrent,
  isFailed,
  isPaused,
  isSelected,
  color,
  onClick,
}: {
  stage: Stage;
  isCompleted: boolean;
  isCurrent: boolean;
  isFailed: boolean;
  isPaused: boolean;
  isSelected: boolean;
  color: (typeof GROUP_COLORS)[string];
  onClick: () => void;
}) {
  const meta = STAGE_META[stage];
  const isActive = isCompleted || isCurrent;

  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center bg-transparent border-none cursor-pointer p-0 group"
      title={`Filter to ${meta.label}`}
    >
      <div
        className={`w-9 h-9 rounded-lg flex items-center justify-center text-[10px] font-bold transition-all duration-300 relative ${
          isSelected ? "ring-2 ring-offset-1 ring-offset-[#0a2234] scale-110" : "group-hover:scale-105"
        }`}
        style={{
          backgroundColor: isFailed
            ? "rgba(255, 65, 87, 0.15)"
            : isPaused
              ? "rgba(240, 184, 50, 0.15)"
              : isActive
                ? color.bg
                : "rgba(27, 40, 51, 0.8)",
          color: isFailed
            ? "#ff4157"
            : isPaused
              ? "#f0b832"
              : isActive
                ? color.accent
                : "#455560",
          borderWidth: "1px",
          borderStyle: "solid",
          borderColor: isFailed
            ? "rgba(255, 65, 87, 0.3)"
            : isPaused
              ? "rgba(240, 184, 50, 0.3)"
              : isActive
                ? color.border
                : "rgba(42, 63, 74, 0.8)",
          boxShadow: isCurrent && !isFailed && !isPaused
            ? `0 0 8px ${color.dim}`
            : isSelected
              ? `0 0 6px ${color.dim}`
              : "none",
          ...(isSelected ? { ringColor: color.accent } : {}),
          animation: isCurrent && !isFailed && !isPaused ? "pulse-glow 2s ease-in-out infinite" : "none",
        }}
      >
        {isCompleted && !isCurrent ? (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M3 7l3 3 5-5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : isFailed ? (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M3 3l6 6M9 3l-6 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          meta.icon
        )}
      </div>
      <span
        className="text-[10px] mt-1.5 text-center leading-tight transition-colors"
        style={{
          color: isFailed
            ? "#ff4157"
            : isPaused
              ? "#f0b832"
              : isActive || isSelected
                ? color.accent
                : "#63717a",
          fontWeight: isCurrent || isSelected ? 600 : 400,
        }}
      >
        {meta.label}
      </span>
    </button>
  );
}

function ForwardArrow({
  filled,
  active,
  color,
}: {
  filled: boolean;
  active: boolean;
  color: (typeof GROUP_COLORS)[string];
}) {
  const stroke = active
    ? color.accent
    : filled
      ? color.dim
      : "rgba(42, 63, 74, 0.8)";

  return (
    <div className="flex-shrink-0 self-start mt-[12px] mx-0.5">
      <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
        <line
          x1="0"
          y1="6"
          x2="14"
          y2="6"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          className={active ? "animate-flow-line" : undefined}
        />
        <polyline
          points="12,2 18,6 12,10"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </div>
  );
}

function GroupForwardArrow({ filled }: { filled: boolean }) {
  const stroke = filled
    ? "rgba(250, 249, 254, 0.15)"
    : "rgba(42, 63, 74, 0.5)";

  return (
    <div className="flex items-start self-end mb-6">
      <svg width="28" height="12" viewBox="0 0 28 12" fill="none">
        <line
          x1="0"
          y1="6"
          x2="20"
          y2="6"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
        />
        <polyline
          points="18,2 26,6 18,10"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </div>
  );
}

interface LoopArc {
  from: Stage;
  to: Stage;
  count: number;
  label: string;
}

function BackwardLoopOverlay({
  containerRef,
  stageRefs,
  loops,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  stageRefs: React.RefObject<Map<string, HTMLElement>>;
  loops: LoopArc[];
}) {
  const [arcs, setArcs] = useState<
    { x1: number; y1: number; x2: number; y2: number; count: number; label: string }[]
  >([]);

  const measure = useCallback(() => {
    const container = containerRef.current;
    const refs = stageRefs.current;
    if (!container || !refs) return;

    const containerRect = container.getBoundingClientRect();
    const newArcs: typeof arcs = [];

    for (const loop of loops) {
      const fromEl = refs.get(loop.from);
      const toEl = refs.get(loop.to);
      if (!fromEl || !toEl) continue;

      const fromRect = fromEl.getBoundingClientRect();
      const toRect = toEl.getBoundingClientRect();

      newArcs.push({
        x1: fromRect.left + fromRect.width / 2 - containerRect.left,
        y1: fromRect.bottom - containerRect.top,
        x2: toRect.left + toRect.width / 2 - containerRect.left,
        y2: toRect.bottom - containerRect.top,
        count: loop.count,
        label: loop.label,
      });
    }

    setArcs(newArcs);
  }, [containerRef, stageRefs, loops]);

  useLayoutEffect(() => {
    measure();

    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => measure());
    observer.observe(container);
    return () => observer.disconnect();
  }, [measure]);

  if (arcs.length === 0) return null;

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      overflow="visible"
    >
      <defs>
        <marker
          id="loop-arrow"
          viewBox="0 0 8 8"
          refX="7"
          refY="4"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M1,1 L7,4 L1,7" fill="none" stroke="#a78bfa" strokeWidth="1.5" />
        </marker>
        <marker
          id="loop-arrow-active"
          viewBox="0 0 8 8"
          refX="7"
          refY="4"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M1,1 L7,4 L1,7" fill="none" stroke="#a78bfa" strokeWidth="1.5" />
        </marker>
      </defs>
      {arcs.map((arc, i) => {
        const isActive = arc.count > 0;
        // Start arcs from bottom of stage icons (+2px gap)
        const startY = Math.max(arc.y1, arc.y2) + 2;
        const arcBottom = startY + 18;
        const midX = (arc.x1 + arc.x2) / 2;

        // Cubic bezier curving below the stages
        const d = `M ${arc.x1} ${startY} C ${arc.x1} ${arcBottom}, ${arc.x2} ${arcBottom}, ${arc.x2} ${startY}`;

        return (
          <g key={i}>
            <path
              d={d}
              fill="none"
              stroke={isActive ? "#a78bfa" : "rgba(167, 139, 250, 0.35)"}
              strokeWidth={isActive ? 2 : 1.5}
              strokeDasharray={isActive ? "none" : "4 3"}
              markerEnd={isActive ? "url(#loop-arrow-active)" : "url(#loop-arrow)"}
            />
            {isActive && (
              <g transform={`translate(${midX}, ${arcBottom + 2})`}>
                <rect
                  x="-14"
                  y="-7"
                  width="28"
                  height="14"
                  rx="7"
                  fill="rgba(167, 139, 250, 0.2)"
                  stroke="rgba(167, 139, 250, 0.4)"
                  strokeWidth="1"
                />
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#a78bfa"
                  fontSize="9"
                  fontWeight="600"
                  fontFamily="-apple-system, BlinkMacSystemFont, sans-serif"
                >
                  {`\u00d7${arc.count}`}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
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
