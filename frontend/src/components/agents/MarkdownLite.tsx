import type React from "react";

export function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let match;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const m = match[0];
    if (m.startsWith("`")) {
      parts.push(
        <code key={key++} className="bg-bg-surface rounded px-1 py-0.5 text-[11px] text-accent font-mono">
          {m.slice(1, -1)}
        </code>
      );
    } else if (m.startsWith("**")) {
      parts.push(<strong key={key++}>{m.slice(2, -2)}</strong>);
    }
    last = match.index + m.length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length === 1 ? parts[0] : parts;
}

export default function MarkdownLite({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  const lines = text.split("\n");
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let codeKey = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        parts.push(
          <pre key={`code-${codeKey++}`} className="bg-bg-surface rounded px-2 py-1.5 text-[11px] text-text-muted overflow-x-auto my-1 whitespace-pre-wrap">
            {codeLines.join("\n")}
          </pre>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }
    parts.push(
      <span key={i}>
        {renderInline(line)}
        {i < lines.length - 1 && "\n"}
      </span>
    );
  }

  // Unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    parts.push(
      <pre key={`code-${codeKey}`} className="bg-bg-surface rounded px-2 py-1.5 text-[11px] text-text-muted overflow-x-auto my-1 whitespace-pre-wrap">
        {codeLines.join("\n")}
      </pre>
    );
  }

  return <div className="text-xs text-text leading-relaxed whitespace-pre-wrap">{parts}</div>;
}
