import { STATUS_COLORS } from "../../utils/statusStyles";

export function CheckmarkIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-label="Completed">
      <circle cx="8" cy="8" r="7" stroke={color} strokeWidth="1.5" opacity="0.4" />
      <path d="M5 8l2 2 4-4" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function FailIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-label="Failed">
      <circle cx="8" cy="8" r="7" stroke={STATUS_COLORS.failed} strokeWidth="1.5" opacity="0.4" />
      <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke={STATUS_COLORS.failed} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function PauseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-label="Paused">
      <circle cx="8" cy="8" r="7" stroke={STATUS_COLORS.paused} strokeWidth="1.5" opacity="0.4" />
      <rect x="6" y="5" width="1.5" height="6" rx="0.5" fill={STATUS_COLORS.paused} />
      <rect x="8.5" y="5" width="1.5" height="6" rx="0.5" fill={STATUS_COLORS.paused} />
    </svg>
  );
}

export function SmallCheckmarkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-label="Completed">
      <path
        d="M3 7l3 3 5-5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SmallFailIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-label="Failed">
      <path
        d="M3 3l6 6M9 3l-6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
