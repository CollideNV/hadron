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

/** Severity badge classes (compact pill style) for summary cards. */
export const SEVERITY_BADGE_CLASSES: Record<string, string> = {
  critical: "bg-severity-critical/10 text-severity-critical",
  major: "bg-severity-major/10 text-severity-major",
  minor: "bg-severity-minor/10 text-severity-minor",
  info: "bg-severity-info/10 text-severity-info",
};

/** Canonical ordering for severity display (most severe first). */
export const SEVERITY_ORDER = ["critical", "major", "minor", "info"] as const;
