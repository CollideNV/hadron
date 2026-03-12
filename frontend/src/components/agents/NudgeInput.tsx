import { useState, useRef, useCallback } from "react";
import { sendNudge } from "../../api/client";

interface NudgeInputProps {
  crId: string;
  role: string;
}

export default function NudgeInput({ crId, role }: NudgeInputProps) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    try {
      await sendNudge(crId, role, trimmed);
      setText("");
    } catch (e) {
      console.error("Failed to send nudge:", e);
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [crId, role, text]);

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-t border-border-subtle bg-bg-surface">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder="Guide this agent..."
        className="flex-1 bg-bg border border-border-subtle rounded px-2 py-1 text-xs text-text placeholder:text-text-dim focus:outline-none focus:border-accent"
        disabled={sending}
      />
      <button
        onClick={handleSend}
        disabled={!text.trim() || sending}
        className="px-2.5 py-1 text-[11px] font-medium bg-accent text-white rounded cursor-pointer border-none disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/90 transition-colors"
      >
        Send
      </button>
    </div>
  );
}
