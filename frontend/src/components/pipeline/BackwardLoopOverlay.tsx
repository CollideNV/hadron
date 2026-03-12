import { useState, useCallback, useLayoutEffect } from "react";
import type { LoopArc } from "./stageTimelineConstants";

export default function BackwardLoopOverlay({
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
