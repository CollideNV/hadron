import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { createRef } from "react";
import BackwardLoopOverlay from "./BackwardLoopOverlay";
import type { LoopArc } from "./stageTimelineConstants";

// --- ResizeObserver mock ---

let resizeObserverInstances: InstanceType<typeof MockResizeObserver>[] = [];

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  constructor(public callback: ResizeObserverCallback) {
    resizeObserverInstances.push(this);
  }
}

beforeEach(() => {
  resizeObserverInstances = [];
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// --- Helpers ---

function mockRect(x: number, y: number, width: number, height: number): DOMRect {
  return {
    x,
    y,
    width,
    height,
    top: y,
    left: x,
    bottom: y + height,
    right: x + width,
    toJSON: () => ({}),
  };
}

function setup(loops: LoopArc[], stageKeys?: string[]) {
  const containerEl = document.createElement("div");
  containerEl.getBoundingClientRect = vi.fn(() => mockRect(0, 0, 800, 100));

  const containerRef = createRef<HTMLDivElement>() as React.MutableRefObject<HTMLDivElement | null>;
  // Directly assign to make it available synchronously before render effects
  (containerRef as { current: HTMLDivElement | null }).current = containerEl;

  const stageMap = new Map<string, HTMLElement>();
  const keys = stageKeys ?? [...new Set(loops.flatMap((l) => [l.from, l.to]))];
  let xPos = 100;
  for (const key of keys) {
    const el = document.createElement("div");
    el.getBoundingClientRect = vi.fn(() => mockRect(xPos, 10, 60, 40));
    stageMap.set(key, el);
    xPos += 120;
  }

  const stageRefs = createRef<Map<string, HTMLElement>>() as React.MutableRefObject<Map<string, HTMLElement>>;
  (stageRefs as { current: Map<string, HTMLElement> }).current = stageMap;

  let result: ReturnType<typeof render>;
  act(() => {
    result = render(
      <BackwardLoopOverlay
        containerRef={containerRef}
        stageRefs={stageRefs}
        loops={loops}
      />,
    );
  });
  return result!;
}

describe("BackwardLoopOverlay", () => {
  it("returns null when loops is empty", () => {
    const { container } = setup([]);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("returns null when stage refs are missing", () => {
    const loops: LoopArc[] = [
      { from: "review", to: "tdd", count: 1, label: "review retry" },
    ];

    // Create refs with no matching stage elements
    const containerEl = document.createElement("div");
    containerEl.getBoundingClientRect = vi.fn(() => mockRect(0, 0, 800, 100));

    const containerRef = createRef<HTMLDivElement>() as React.MutableRefObject<HTMLDivElement | null>;
    (containerRef as { current: HTMLDivElement | null }).current = containerEl;

    const stageRefs = createRef<Map<string, HTMLElement>>() as React.MutableRefObject<Map<string, HTMLElement>>;
    (stageRefs as { current: Map<string, HTMLElement> }).current = new Map(); // empty — no matching refs

    let result: ReturnType<typeof render>;
    act(() => {
      result = render(
        <BackwardLoopOverlay
          containerRef={containerRef}
          stageRefs={stageRefs}
          loops={loops}
        />,
      );
    });

    expect(result!.container.querySelector("svg")).toBeNull();
  });

  it("renders SVG paths when refs are available", () => {
    const loops: LoopArc[] = [
      { from: "review", to: "tdd", count: 2, label: "review retry" },
    ];

    const { container } = setup(loops, ["review", "tdd"]);

    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();

    // defs contain marker paths + one arc path
    const arcPaths = svg!.querySelectorAll("g > path");
    expect(arcPaths.length).toBeGreaterThanOrEqual(1);
  });

  it("active arcs (count > 0) have count badge text", () => {
    const loops: LoopArc[] = [
      { from: "review", to: "tdd", count: 3, label: "review retry" },
    ];

    const { container } = setup(loops, ["review", "tdd"]);

    const texts = container.querySelectorAll("text");
    const badgeTexts = Array.from(texts).map((t) => t.textContent);
    // The badge shows ×3 (using unicode multiply sign \u00d7)
    expect(badgeTexts).toContain("\u00d73");
  });

  it("inactive arcs (count === 0) have no count badge", () => {
    const loops: LoopArc[] = [
      { from: "behaviour_verification", to: "behaviour_translation", count: 0, label: "spec retry" },
    ];

    const { container } = setup(loops, ["behaviour_verification", "behaviour_translation"]);

    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();

    // No text elements for badges on inactive arcs
    const texts = svg!.querySelectorAll("text");
    expect(texts).toHaveLength(0);
  });

  it("ResizeObserver is connected on mount and disconnected on unmount", () => {
    const loops: LoopArc[] = [
      { from: "review", to: "tdd", count: 1, label: "review retry" },
    ];

    const result = setup(loops, ["review", "tdd"]);

    // Observer was created
    expect(resizeObserverInstances.length).toBeGreaterThanOrEqual(1);
    const observer = resizeObserverInstances[resizeObserverInstances.length - 1];

    // Unmount triggers disconnect
    result.unmount();
    expect(observer.disconnect).toHaveBeenCalled();
  });
});
