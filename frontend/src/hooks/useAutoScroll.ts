import { useRef, useEffect, useCallback } from "react";

const NEAR_BOTTOM_THRESHOLD = 80; // px

/**
 * Auto-scroll a container to the bottom when content changes,
 * but only if the user hasn't scrolled up to read previous content.
 *
 * Returns a ref to attach to the scrollable container and an onScroll handler.
 */
export function useAutoScroll<T extends HTMLElement>(
  deps: unknown[],
): {
  scrollRef: React.RefObject<T | null>;
  onScroll: () => void;
} {
  const scrollRef = useRef<T | null>(null);
  const isNearBottom = useRef(true);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    isNearBottom.current = distanceFromBottom <= NEAR_BOTTOM_THRESHOLD;
  }, []);

  useEffect(() => {
    if (isNearBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { scrollRef, onScroll };
}
