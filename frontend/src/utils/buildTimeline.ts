import type { PipelineEvent } from "../api/types";
import type { ConversationItem } from "../components/agents/types";

export type TimelineItem =
  | { kind: "output"; item: Extract<ConversationItem, { type: "output" }>; ts: number; id: string }
  | { kind: "tool"; call: Extract<ConversationItem, { type: "tool_call" }>; result?: Extract<ConversationItem, { type: "tool_result" }>; ts: number; id: string }
  | { kind: "nudge"; item: Extract<ConversationItem, { type: "nudge" }>; ts: number; id: string }
  | { kind: "phase_started"; item: Extract<ConversationItem, { type: "phase_started" }>; ts: number; id: string }
  | { kind: "prompt"; item: Extract<ConversationItem, { type: "prompt" }>; ts: number; id: string }
  | { kind: "test_run"; event: PipelineEvent; ts: number; id: string }
  | { kind: "finding"; event: PipelineEvent; ts: number; id: string };

export function buildTimeline(
  items: ConversationItem[],
  testRuns: PipelineEvent[],
  findings: PipelineEvent[],
): TimelineItem[] {
  const timeline: TimelineItem[] = [];
  let seq = 0;

  // Pair tool calls with results via sequential scan
  let i = 0;
  while (i < items.length) {
    const item = items[i];
    if (item.type === "output") {
      timeline.push({ kind: "output", item, ts: item.ts, id: `out-${seq++}` });
    } else if (item.type === "tool_call") {
      // Check if next item is the matching tool_result
      const next = items[i + 1];
      if (next && next.type === "tool_result" && next.tool === item.tool) {
        timeline.push({ kind: "tool", call: item, result: next, ts: item.ts, id: `tool-${seq++}` });
        i++; // skip the result
      } else {
        timeline.push({ kind: "tool", call: item, ts: item.ts, id: `tool-${seq++}` });
      }
    } else if (item.type === "tool_result") {
      // Orphan result — render as a fallback tool entry
      timeline.push({
        kind: "tool",
        call: { type: "tool_call", tool: item.tool, input: {}, round: item.round, ts: item.ts },
        result: item,
        ts: item.ts,
        id: `tool-orphan-${seq++}`,
      });
    } else if (item.type === "nudge") {
      timeline.push({ kind: "nudge", item, ts: item.ts, id: `nudge-${seq++}` });
    } else if (item.type === "phase_started") {
      timeline.push({ kind: "phase_started", item, ts: item.ts, id: `phase-${item.phase}` });
    } else if (item.type === "prompt") {
      timeline.push({ kind: "prompt", item, ts: item.ts, id: `prompt-${seq++}` });
    }
    i++;
  }

  // Interleave test runs and findings by timestamp
  for (const tr of testRuns) {
    timeline.push({ kind: "test_run", event: tr, ts: tr.timestamp, id: `test-${tr.timestamp}-${seq++}` });
  }
  for (const f of findings) {
    timeline.push({ kind: "finding", event: f, ts: f.timestamp, id: `finding-${f.timestamp}-${seq++}` });
  }

  // Sort everything by timestamp
  timeline.sort((a, b) => a.ts - b.ts);
  return timeline;
}
