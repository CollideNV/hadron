import type { Stage } from "../../api/types";

export const GROUP_COLORS: Record<string, { accent: string; bg: string; border: string; dim: string }> = {
  Understand: {
    accent: "#4dc9f6",   // cyan
    bg: "rgba(77, 201, 246, 0.12)",
    border: "rgba(77, 201, 246, 0.25)",
    dim: "rgba(77, 201, 246, 0.5)",
  },
  Specify: {
    accent: "#a78bfa",   // violet
    bg: "rgba(167, 139, 250, 0.12)",
    border: "rgba(167, 139, 250, 0.25)",
    dim: "rgba(167, 139, 250, 0.5)",
  },
  Build: {
    accent: "#37e284",   // green (Collide accent)
    bg: "rgba(55, 226, 132, 0.12)",
    border: "rgba(55, 226, 132, 0.25)",
    dim: "rgba(55, 226, 132, 0.5)",
  },
  Validate: {
    accent: "#f0b832",   // amber
    bg: "rgba(240, 184, 50, 0.12)",
    border: "rgba(240, 184, 50, 0.25)",
    dim: "rgba(240, 184, 50, 0.5)",
  },
  Ship: {
    accent: "#f472b6",   // pink
    bg: "rgba(244, 114, 182, 0.12)",
    border: "rgba(244, 114, 182, 0.25)",
    dim: "rgba(244, 114, 182, 0.5)",
  },
};

export const STAGE_META: Record<
  Stage,
  { label: string; icon: string; group: string }
> = {
  intake: { label: "Intake", icon: "IN", group: "Understand" },
  repo_id: { label: "Repo ID", icon: "ID", group: "Understand" },
  worktree_setup: { label: "Worktree", icon: "WT", group: "Understand" },
  behaviour_translation: { label: "Translate", icon: "BT", group: "Specify" },
  behaviour_verification: { label: "Verify", icon: "BV", group: "Specify" },
  implementation: { label: "Implement", icon: "IM", group: "Build" },
  e2e_testing: { label: "E2E", icon: "E2", group: "Build" },
  review: { label: "Review", icon: "RV", group: "Validate" },
  rebase: { label: "Rebase", icon: "RB", group: "Validate" },
  delivery: { label: "Deliver", icon: "DL", group: "Ship" },
  release_gate: { label: "Gate", icon: "GT", group: "Ship" },
  release: { label: "Release", icon: "RL", group: "Ship" },
  retrospective: { label: "Retro", icon: "RT", group: "Ship" },
};

export const GROUPS = ["Understand", "Specify", "Build", "Validate", "Ship"];

export const FEEDBACK_LOOPS: {
  from: Stage;
  to: Stage;
  label: string;
  countKey: "behaviour_translation" | "implementation";
}[] = [
  {
    from: "behaviour_verification",
    to: "behaviour_translation",
    label: "spec retry",
    countKey: "behaviour_translation",
  },
  {
    from: "review",
    to: "implementation",
    label: "review retry",
    countKey: "implementation",
  },
];

export interface LoopArc {
  from: Stage;
  to: Stage;
  count: number;
  label: string;
}

export type GroupColor = (typeof GROUP_COLORS)[string];
