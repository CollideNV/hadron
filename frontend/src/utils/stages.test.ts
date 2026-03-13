import { describe, it, expect } from "vitest";
import { getStageColor, STAGE_GROUP, GROUP_ACCENT, STAGE_LABEL } from "./stages";

describe("getStageColor", () => {
  it("returns correct color for known stage", () => {
    expect(getStageColor("intake")).toBe(GROUP_ACCENT.Understand);
  });

  it("returns correct color for implementation stage", () => {
    expect(getStageColor("implementation")).toBe(GROUP_ACCENT.Build);
  });

  it("returns correct color for review stage", () => {
    expect(getStageColor("review")).toBe(GROUP_ACCENT.Validate);
  });

  it("returns correct color for delivery stage", () => {
    expect(getStageColor("delivery")).toBe(GROUP_ACCENT.Ship);
  });

  it("handles stage:repo format by extracting base stage", () => {
    expect(getStageColor("implementation:backend")).toBe(GROUP_ACCENT.Build);
  });

  it("returns Build color for unknown stage", () => {
    expect(getStageColor("unknown_stage")).toBe(GROUP_ACCENT.Build);
  });

  it("handles empty string", () => {
    expect(getStageColor("")).toBe(GROUP_ACCENT.Build);
  });
});

describe("STAGE_GROUP", () => {
  it("maps all expected stages", () => {
    const expectedStages = [
      "intake", "repo_id", "worktree_setup",
      "behaviour_translation", "behaviour_verification",
      "implementation", "review", "rebase",
      "delivery", "release_gate", "release", "retrospective",
    ];
    for (const stage of expectedStages) {
      expect(STAGE_GROUP[stage]).toBeDefined();
    }
  });
});

describe("STAGE_LABEL", () => {
  it("has a label for every stage in STAGE_GROUP", () => {
    for (const stage of Object.keys(STAGE_GROUP)) {
      expect(STAGE_LABEL[stage]).toBeDefined();
    }
  });
});
