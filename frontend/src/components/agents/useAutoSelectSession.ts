import { useState, useEffect, useRef } from "react";
import type { AgentSession } from "./types";

/**
 * Manages session selection with auto-select behavior:
 * selects the latest active (non-completed) session when one appears,
 * but does not override a manual user selection.
 */
export function useAutoSelectSession(sessions: AgentSession[]) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const userSelected = useRef(false);
  const prevSessionCount = useRef(sessions.length);

  const handleSelect = (index: number) => {
    userSelected.current = true;
    setSelectedIndex(index);
  };

  useEffect(() => {
    // Reset user selection lock when new sessions appear
    if (sessions.length > prevSessionCount.current) {
      userSelected.current = false;
    }
    prevSessionCount.current = sessions.length;

    if (userSelected.current) return;

    let lastActive = -1;
    for (let i = sessions.length - 1; i >= 0; i--) {
      if (!sessions[i].completed) {
        lastActive = i;
        break;
      }
    }
    if (lastActive >= 0 && lastActive !== selectedIndex) {
      setSelectedIndex(lastActive);
    }
  }, [sessions, selectedIndex]);

  const selectedSession = sessions[selectedIndex] as AgentSession | undefined;

  return { selectedIndex, selectedSession, setSelectedIndex: handleSelect } as const;
}
