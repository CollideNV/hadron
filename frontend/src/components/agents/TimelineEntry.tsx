import { formatModelName } from "../../utils/format";
import RichToolCall from "./ToolRenderers";
import MarkdownLite from "./MarkdownLite";
import { InlineTestRun, InlineFinding } from "./InlineEventCards";
import type { TimelineItem } from "../../utils/buildTimeline";

export const PHASE_LABELS: Record<string, string> = {
  explore: "Explore",
  plan: "Plan",
  act: "Execute",
};

interface TimelineEntryProps {
  entry: TimelineItem;
  idx: number;
  selectedPhase: string | null;
}

export default function TimelineEntry({ entry, idx, selectedPhase }: TimelineEntryProps) {
  const key = `${entry.kind}-${entry.ts}-${idx}`;

  if (entry.kind === "phase_started" && !selectedPhase) {
    return (
      <div key={key} className="flex items-center gap-2 py-1">
        <div className="flex-1 border-t border-border-subtle" />
        <span className="text-[10px] text-text-dim font-medium uppercase tracking-wide">
          {PHASE_LABELS[entry.item.phase] || entry.item.phase}
        </span>
        <span className="text-[10px] text-text-muted font-mono">
          {formatModelName(entry.item.model)}
        </span>
        <div className="flex-1 border-t border-border-subtle" />
      </div>
    );
  }
  if (entry.kind === "prompt") {
    return (
      <div key={key} className="animate-fade-in">
        <details className="group">
          <summary className="flex items-start gap-2 cursor-pointer list-none">
            <span className="text-[11px] flex-shrink-0 mt-0.5">&#128203;</span>
            <span className="text-xs text-text-dim italic">Task prompt</span>
            <span className="text-[10px] text-text-muted ml-1">(click to expand)</span>
          </summary>
          <div className="ml-6 mt-1">
            <MarkdownLite text={entry.item.text} />
          </div>
        </details>
      </div>
    );
  }
  if (entry.kind === "output") {
    return (
      <div key={key} className="animate-fade-in">
        <div className="flex items-start gap-2">
          <span className="text-[11px] flex-shrink-0 mt-0.5">&#129302;</span>
          <MarkdownLite text={entry.item.text} />
        </div>
      </div>
    );
  }
  if (entry.kind === "tool") {
    return (
      <div key={key} className="animate-fade-in">
        <RichToolCall call={entry.call} result={entry.result} />
      </div>
    );
  }
  if (entry.kind === "nudge") {
    return (
      <div key={key} className="animate-fade-in">
        <div className="flex items-start gap-2">
          <span className="text-[11px] flex-shrink-0 mt-0.5">&#128100;</span>
          <p className="text-xs text-text leading-relaxed bg-accent/10 rounded px-2 py-1 border border-accent/20">
            {entry.item.text}
          </p>
        </div>
      </div>
    );
  }
  if (entry.kind === "test_run") {
    return (
      <div key={key} className="animate-fade-in">
        <InlineTestRun event={entry.event} />
      </div>
    );
  }
  if (entry.kind === "finding") {
    return (
      <div key={key} className="animate-fade-in">
        <InlineFinding event={entry.event} />
      </div>
    );
  }
  return null;
}
