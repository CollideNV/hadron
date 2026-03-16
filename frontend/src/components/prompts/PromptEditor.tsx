import { useCallback, useRef, useEffect } from "react";
import { BTN_ACCENT, BTN_GHOST } from "../../utils/styles";

interface PromptEditorProps {
  content: string;
  onChange: (content: string) => void;
  onSave: () => void;
  onDiscard: () => void;
  dirty: boolean;
  saving: boolean;
}

function highlightMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^(#{1,6}\s.*)$/gm, '<span class="text-accent font-semibold">$1</span>')
    .replace(/^(```\w*)$/gm, '<span class="text-text-dim">$1</span>')
    .replace(/^(- .*)$/gm, '<span class="text-text-muted">$1</span>')
    .replace(/\*\*([^*]+)\*\*/g, '<span class="text-text font-bold">**$1**</span>');
}

export default function PromptEditor({
  content,
  onChange,
  onSave,
  onDiscard,
  dirty,
  saving,
}: PromptEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);

  const syncScroll = useCallback(() => {
    if (textareaRef.current && preRef.current) {
      preRef.current.scrollTop = textareaRef.current.scrollTop;
      preRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  }, []);

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.addEventListener("scroll", syncScroll);
      return () => ta.removeEventListener("scroll", syncScroll);
    }
  }, [syncScroll]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-text-dim">
          {content.length} characters
        </span>
        <div className="flex gap-2">
          <button
            className={BTN_GHOST}
            onClick={onDiscard}
            disabled={!dirty}
          >
            Discard
          </button>
          <button
            className={BTN_ACCENT}
            onClick={onSave}
            disabled={!dirty || saving}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
      <div className="relative flex-1 min-h-0">
        <pre
          ref={preRef}
          className="absolute inset-0 overflow-auto m-0 p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap break-words pointer-events-none border border-border rounded-lg bg-bg"
          aria-hidden="true"
          dangerouslySetInnerHTML={{
            __html: highlightMarkdown(content) + "\n",
          }}
        />
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="absolute inset-0 w-full h-full resize-none m-0 p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap break-words border border-border rounded-lg bg-transparent text-transparent caret-text focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/40"
        />
      </div>
    </div>
  );
}
