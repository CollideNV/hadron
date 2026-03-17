import { test, expect } from "@playwright/test";

const CR_ID = "CR-demo-001";

/** Navigate to a CR and wait for the event stream to finish. */
async function openCR(page: import("@playwright/test").Page) {
  await page.goto(`/cr/${CR_ID}`);
  await expect(page.getByTestId("cr-status")).toHaveText("completed", { timeout: 15_000 });
}

/** Click a stage in the timeline by its data-testid, then wait for the detail sidebar. */
async function openStage(page: import("@playwright/test").Page, stage: string) {
  await page.getByTestId(`stage-${stage}`).click();
  await expect(page.getByTestId("back-button")).toBeVisible();
}

// ---------------------------------------------------------------------------
// Navigation & Layout
// ---------------------------------------------------------------------------

test.describe("Navigation", () => {
  test("top nav links navigate between pages", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Pipeline Runs")).toBeVisible();

    // Navigate to Settings
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL("/settings");
    await expect(page.getByText("Model Settings")).toBeVisible();

    // Navigate to Prompts
    await page.getByTestId("nav-prompts").click();
    await expect(page).toHaveURL("/prompts");
    await expect(page.getByText("Prompt Templates")).toBeVisible();

    // Back to Pipelines
    await page.getByTestId("nav-pipelines").click();
    await expect(page).toHaveURL("/");
    await expect(page.getByText("Pipeline Runs")).toBeVisible();
  });

  test("CR list → CR detail → back to list", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId(`cr-card-${CR_ID}`).click();
    await expect(page).toHaveURL(`/cr/${CR_ID}`);
    await expect(page.getByText(CR_ID)).toBeVisible();

    // Back arrow link
    await page.locator("a[href='/']").first().click();
    await expect(page).toHaveURL("/");
    await expect(page.getByText("Pipeline Runs")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Pipeline Dashboard
// ---------------------------------------------------------------------------

test.describe("Pipeline Dashboard", () => {
  test("CR list shows the demo CR", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(CR_ID)).toBeVisible();
    await expect(page.getByText("Add user authentication with JWT tokens")).toBeVisible();
  });

  test("CR detail page streams events and reaches completed", async ({ page }) => {
    await openCR(page);
    await expect(page.getByText(/\$0\.\d+/)).toBeVisible();
  });

  test("clicking a stage shows agent sessions and tabs", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    await expect(page.getByTestId("tab-conversation")).toBeVisible();
    await expect(page.getByTestId("tab-changes")).toBeVisible();
  });

  test("back button returns to overview", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    await page.getByTestId("back-button").click();
    // Should see the event log overview (stage list), not the detail view
    await expect(page.getByText("Pipeline Stages")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Event Log Overview
// ---------------------------------------------------------------------------

test.describe("Event Log Overview", () => {
  test("shows stage list with correct count", async ({ page }) => {
    await openCR(page);
    await expect(page.getByText("Pipeline Stages")).toBeVisible();
    // Dummy server covers intake through delivery
    await expect(page.getByText(/\d+ stages?/)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Stage Detail — Conversation
// ---------------------------------------------------------------------------

test.describe("Stage Conversation", () => {
  test("implementation stage shows agent session in sidebar", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    // Session sidebar should list the implementation session (role: "implementation")
    await expect(page.getByText("implementation").first()).toBeVisible({ timeout: 10_000 });

    // Conversation tab should be active (selected)
    await expect(page.getByTestId("tab-conversation")).toHaveClass(/text-accent/);
  });

  test("implementation session shows phase tabs (explore/plan/execute)", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    // Phase tabs: Explore, Plan, Execute (labels from PHASE_LABELS)
    await expect(page.getByRole("button", { name: /Explore/ }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /Plan/ }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Execute/ })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Stage Summary
// ---------------------------------------------------------------------------

test.describe("Stage Summary", () => {
  test("implementation stage shows duration and cost", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    await expect(page.getByText("Duration").first()).toBeVisible();
    await expect(page.getByText("Cost").first()).toBeVisible();
  });

  test("implementation stage shows test results", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    // Test badges: dummy server has test_run events for implementation
    await expect(page.getByText(/\d+ passed/)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Stage Diff Viewer
// ---------------------------------------------------------------------------

test.describe("Stage Diff Viewer", () => {
  test("behaviour translation shows feature files in Changes tab", async ({ page }) => {
    await openCR(page);
    await openStage(page, "behaviour_translation");

    await page.getByTestId("tab-changes").click();

    await expect(page.getByTestId("feature-specs-header")).toBeVisible();
    await expect(page.getByText("features/auth.feature").first()).toBeVisible();
    await expect(page.getByText("User Authentication").first()).toBeVisible();
  });

  test("implementation shows code diff in Changes tab", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    await page.getByTestId("tab-changes").click();

    await expect(page.getByTestId("code-diff-header")).toBeVisible();
    await expect(page.getByText(/files? changed/)).toBeVisible();
    await expect(page.getByText("src/auth/jwt.py").first()).toBeVisible();
    await expect(page.getByText("src/auth/router.py").first()).toBeVisible();
    await expect(page.getByText("tests/test_auth.py").first()).toBeVisible();
  });

  test("review shows both diff and feature specs in Changes tab", async ({ page }) => {
    await openCR(page);
    await openStage(page, "review");

    await page.getByTestId("tab-changes").click();

    await expect(page.getByTestId("feature-specs-header")).toBeVisible();
    await expect(page.getByTestId("code-diff-header")).toBeVisible();
  });

  test("stages without diffs show no-changes message", async ({ page }) => {
    await openCR(page);
    await openStage(page, "intake");

    await page.getByTestId("tab-changes").click();
    await expect(page.getByText("(no changes captured)")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Review Rounds
// ---------------------------------------------------------------------------

test.describe("Review Rounds", () => {
  test("review stage shows round tabs", async ({ page }) => {
    await openCR(page);
    await openStage(page, "review");

    await expect(page.getByTestId("round-tab-all")).toBeVisible();
    await expect(page.getByTestId("round-tab-1")).toBeVisible();
    await expect(page.getByTestId("round-tab-2")).toBeVisible();
  });

  test("All view shows round group headers in session list", async ({ page }) => {
    await openCR(page);
    await openStage(page, "review");

    await page.getByTestId("round-tab-all").click();

    await expect(page.getByTestId("round-header-1")).toBeVisible();
    await expect(page.getByTestId("round-header-2")).toBeVisible();
  });

  test("review round 1 shows major finding, round 2 shows info", async ({ page }) => {
    await openCR(page);
    await openStage(page, "review");

    await page.getByTestId("round-tab-1").click();
    await expect(page.getByText("1 major")).toBeVisible();

    await page.getByTestId("round-tab-2").click();
    await expect(page.getByText("1 info")).toBeVisible();
  });

  test("non-review stages do not show round tabs", async ({ page }) => {
    await openCR(page);
    await openStage(page, "implementation");

    await expect(page.getByTestId("round-tab-all")).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Logs Panel
// ---------------------------------------------------------------------------

test.describe("Logs Panel", () => {
  test("logs toggle shows and hides log drawer", async ({ page }) => {
    await openCR(page);

    // Logs panel should not be visible initially
    await expect(page.getByTestId("logs-panel")).not.toBeVisible();

    // Click Logs button
    await page.getByTestId("logs-toggle").click();
    await expect(page.getByTestId("logs-panel")).toBeVisible();
    await expect(page.getByText("Worker Logs")).toBeVisible();

    // Toggle off
    await page.getByTestId("logs-toggle").click();
    await expect(page.getByTestId("logs-panel")).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Settings Page
// ---------------------------------------------------------------------------

test.describe("Settings Page", () => {
  test("loads and displays model settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Model Settings")).toBeVisible();
    // Should show backend/model grid (dummy server returns settings data)
    await expect(page.getByText("Default Backend")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Prompts Page
// ---------------------------------------------------------------------------

test.describe("Prompts Page", () => {
  test("loads and displays prompt template list", async ({ page }) => {
    await page.goto("/prompts");
    await expect(page.getByText("Prompt Templates")).toBeVisible();
    // Dummy server returns prompt templates
    await expect(page.getByText("Spec Writer")).toBeVisible({ timeout: 5_000 });
  });

  test("clicking a prompt loads its content", async ({ page }) => {
    await page.goto("/prompts");
    await page.getByText("Spec Writer").click();
    // Editor should show the prompt content
    await expect(page.locator("textarea")).toBeVisible();
  });
});
