/** Polling interval for list/detail/log views (ms). */
export const POLL_INTERVAL_MS = 5000;

/** Delay before auto-closing success modals (ms). */
export const MODAL_SUCCESS_DELAY_MS = 1500;

/**
 * Tailwind class strings keyed by review-finding severity.
 * Shared between ReviewFindingsPanel and InlineEventCards.
 */
export const SEVERITY_STYLES: Record<string, string> = {
  critical: "text-severity-critical border-severity-critical/20 bg-severity-critical/8",
  major: "text-severity-major border-severity-major/20 bg-severity-major/8",
  minor: "text-severity-minor border-severity-minor/20 bg-severity-minor/8",
  info: "text-severity-info border-severity-info/20 bg-severity-info/8",
};
