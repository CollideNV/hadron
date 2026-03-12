import type { ConversationItem } from "../types";

export type ToolCallItem = Extract<ConversationItem, { type: "tool_call" }>;
export type ToolResultItem = Extract<ConversationItem, { type: "tool_result" }>;

export interface RichToolCallProps {
  call: ToolCallItem;
  result?: ToolResultItem;
}

export function getInput(call: ToolCallItem): Record<string, unknown> {
  if (typeof call.input === "object" && call.input !== null) {
    return call.input as Record<string, unknown>;
  }
  return {};
}

export function addLineNumbers(text: string): string {
  const lines = text.split("\n");
  if (lines.length <= 1) return text;
  const width = String(lines.length).length;
  return lines
    .map((line, i) => `${String(i + 1).padStart(width)} | ${line}`)
    .join("\n");
}

export function extractExitCode(result: string): number | null {
  const match = result.match(/exit[_ ]code[:\s]+(\d+)/i);
  if (match) return parseInt(match[1], 10);
  // Check if result ends with a line like "0" or "1"
  const lines = result.trim().split("\n");
  const last = lines[lines.length - 1]?.trim();
  if (last && /^exit \d+$/.test(last)) return parseInt(last.split(" ")[1], 10);
  return null;
}

export function countMatches(result: string): number {
  return result.split("\n").filter((l) => l.trim()).length;
}
