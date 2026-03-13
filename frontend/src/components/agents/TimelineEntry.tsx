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

/* ---------- Per-kind renderers ---------- */

function PhaseStartedEntry({ entry }: { entry: Extract<TimelineItem, { kind: "phase_started" }> }) {
  return (
    <div className="flex items-center gap-2 py-1">
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

function PromptEntry({ entry }: { entry: Extract<TimelineItem, { kind: "prompt" }> }) {
  return (
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
  );
}

function OutputEntry({ entry }: { entry: Extract<TimelineItem, { kind: "output" }> }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-[11px] flex-shrink-0 mt-0.5">&#129302;</span>
      <MarkdownLite text={entry.item.text} />
    </div>
  );
}

function ToolEntry({ entry }: { entry: Extract<TimelineItem, { kind: "tool" }> }) {
  return <RichToolCall call={entry.call} result={entry.result} />;
}

function NudgeEntry({ entry }: { entry: Extract<TimelineItem, { kind: "nudge" }> }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-[11px] flex-shrink-0 mt-0.5">&#128100;</span>
      <p className="text-xs text-text leading-relaxed bg-accent/10 rounded px-2 py-1 border border-accent/20">
        {entry.item.text}
      </p>
    </div>
  );
}

function TestRunEntry({ entry }: { entry: Extract<TimelineItem, { kind: "test_run" }> }) {
  return <InlineTestRun event={entry.event} />;
}

function FindingEntry({ entry }: { entry: Extract<TimelineItem, { kind: "finding" }> }) {
  return <InlineFinding event={entry.event} />;
}

/* ---------- Registry ---------- */

const ENTRY_RENDERERS: Record<TimelineItem["kind"], React.FC<{ entry: any }>> = {
  phase_started: PhaseStartedEntry,
  prompt: PromptEntry,
  output: OutputEntry,
  tool: ToolEntry,
  nudge: NudgeEntry,
  test_run: TestRunEntry,
  finding: FindingEntry,
};

/* ---------- Main component ---------- */

export default function TimelineEntry({ entry, selectedPhase }: TimelineEntryProps) {
  // Phase dividers are hidden when a specific phase is selected
  if (entry.kind === "phase_started" && selectedPhase) return null;

  const Renderer = ENTRY_RENDERERS[entry.kind];
  if (!Renderer) return null;

  return (
    <div className="animate-fade-in">
      <Renderer entry={entry} />
    </div>
  );
}
