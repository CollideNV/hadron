export const STAGE_GROUP: Record<string, string> = {
  intake: "Understand",
  repo_id: "Understand",
  worktree_setup: "Understand",
  behaviour_translation: "Specify",
  behaviour_verification: "Specify",
  implementation: "Build",
  e2e_testing: "Build",
  review: "Validate",
  rebase: "Validate",
  delivery: "Ship",
  release_gate: "Ship",
  release: "Ship",
  retrospective: "Ship",
};

export const GROUP_ACCENT: Record<string, string> = {
  Understand: "#4dc9f6",
  Specify: "#a78bfa",
  Build: "#37e284",
  Validate: "#f0b832",
  Ship: "#f472b6",
};

export const STAGE_LABEL: Record<string, string> = {
  intake: "Intake",
  repo_id: "Repo ID",
  worktree_setup: "Worktree Setup",
  behaviour_translation: "Behaviour Translation",
  behaviour_verification: "Behaviour Verification",
  implementation: "Implementation",
  e2e_testing: "E2E Testing",
  review: "Code Review",
  rebase: "Rebase",
  delivery: "Delivery",
  release_gate: "Release Gate",
  release: "Release",
  retrospective: "Retrospective",
};

export function getStageColor(stageName: string): string {
  const baseStage = stageName.split(":")[0];
  const group = STAGE_GROUP[baseStage] || "Build";
  return GROUP_ACCENT[group] || "#37e284";
}
