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

    // Navigate to Audit
    await page.getByTestId("nav-audit").click();
    await expect(page).toHaveURL("/audit");
    await expect(page.getByText("Audit Log")).toBeVisible();

    // Navigate to Settings
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL("/settings");
    await expect(page.getByRole("heading", { name: "Backend Templates" })).toBeVisible();

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
// Retrospective
// ---------------------------------------------------------------------------

test.describe("Retrospective", () => {
  test("retrospective stage is marked completed after stream finishes", async ({ page }) => {
    await openCR(page);
    // The retrospective event should mark the stage as completed
    await expect(page.getByTestId("stage-retrospective")).toBeVisible();
  });

  test("clicking retrospective stage shows insight cards", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("stage-retrospective").click();
    await expect(page.getByTestId("back-button")).toBeVisible();

    // Should show insight cards from the dummy server retrospective data
    await expect(page.getByTestId("insights-list")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Excessive review/rework cycling")).toBeVisible();
    await expect(page.getByText("Rework did not reduce blocking findings")).toBeVisible();
    await expect(page.getByText("dominated pipeline time")).toBeVisible();
  });

  test("retrospective shows severity badges", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("stage-retrospective").click();
    await expect(page.getByTestId("insights-list")).toBeVisible({ timeout: 10_000 });

    // Should show severity labels
    await expect(page.getByText("Warning").first()).toBeVisible();
    await expect(page.getByText("Info").first()).toBeVisible();
  });

  test("retrospective shows category tags", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("stage-retrospective").click();
    await expect(page.getByTestId("insights-list")).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText("Quality").first()).toBeVisible();
    await expect(page.getByText("Cost").first()).toBeVisible();
  });

  test("retrospective shows summary bar with status and cost", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("stage-retrospective").click();
    await expect(page.getByTestId("insights-list")).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText("Status:")).toBeVisible();
    await expect(page.getByText("Cost:")).toBeVisible();
    await expect(page.getByText("3 insights")).toBeVisible();
  });

  test("retrospective back button returns to overview", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("stage-retrospective").click();
    await expect(page.getByTestId("back-button")).toBeVisible();

    await page.getByTestId("back-button").click();
    await expect(page.getByText("Pipeline Stages")).toBeVisible();
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
// Cost Dashboard
// ---------------------------------------------------------------------------

test.describe("Cost Dashboard", () => {
  test("clicking cost tracker opens the cost breakdown modal", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("cost-tracker").click();
    await expect(page.getByText("Cost Breakdown")).toBeVisible();
    await expect(page.getByText("Total Pipeline Cost")).toBeVisible();
  });

  test("cost dashboard shows by-stage breakdown", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("cost-tracker").click();
    await expect(page.getByText("By Stage")).toBeVisible();
    await expect(page.getByText("Implement")).toBeVisible();
    await expect(page.getByText("Review")).toBeVisible();
  });

  test("cost dashboard shows by-model breakdown", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("cost-tracker").click();
    await expect(page.getByText("By Model")).toBeVisible();
  });

  test("cost dashboard closes on escape", async ({ page }) => {
    await openCR(page);
    await page.getByTestId("cost-tracker").click();
    await expect(page.getByText("Cost Breakdown")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByText("Cost Breakdown")).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Settings Page
// ---------------------------------------------------------------------------

test.describe("Settings Page", () => {
  test("loads and displays backend templates", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Backend Templates")).toBeVisible();
    // Should show template tabs
    await expect(page.getByTestId("template-tab-anthropic")).toBeVisible();
    await expect(page.getByTestId("template-tab-openai")).toBeVisible();
    await expect(page.getByTestId("template-tab-gemini")).toBeVisible();
  });

  test("selecting a template shows its models in the grid", async ({ page }) => {
    await page.goto("/settings");
    await page.getByTestId("template-tab-openai").click();
    await expect(page.getByTestId("template-stage-grid")).toBeVisible();
  });

  test("shows pipeline defaults section", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Pipeline Defaults")).toBeVisible();
    await expect(page.getByTestId("defaults-max-cost-usd")).toBeVisible();
    await expect(page.getByTestId("defaults-delivery-strategy")).toBeVisible();
    await expect(page.getByTestId("defaults-agent-timeout")).toBeVisible();
  });

  test("editing a pipeline default enables save button", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByTestId("defaults-max-cost-usd")).toBeVisible();

    // Save button should be disabled initially
    const saveBtn = page.getByRole("button", { name: "Save" });
    await expect(saveBtn).toBeDisabled();

    // Change a value
    await page.getByTestId("defaults-max-cost-usd").fill("25");
    await expect(saveBtn).toBeEnabled();

    // Discard should also appear
    await expect(page.getByRole("button", { name: "Discard" })).toBeVisible();
  });

  test("default template has badge", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByTestId("default-badge")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Audit Log Page
// ---------------------------------------------------------------------------

test.describe("Audit Log Page", () => {
  test("navigates to audit log from nav", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-audit").click();
    await expect(page).toHaveURL("/audit");
    await expect(page.getByText("Audit Log")).toBeVisible();
  });

  test("displays audit entries with timestamps and actions", async ({ page }) => {
    await page.goto("/audit");
    const table = page.locator("table");
    await expect(table.getByText("backend templates updated")).toBeVisible();
    await expect(table.getByText("pipeline defaults updated")).toBeVisible();
    await expect(table.getByText("api key updated")).toBeVisible();
  });

  test("filter by action type", async ({ page }) => {
    await page.goto("/audit");
    const table = page.locator("table");
    await page.getByTestId("audit-filter-backend_templates_updated").click();
    // Only backend_templates_updated entries should be visible in the table
    await expect(table.getByText("backend templates updated").first()).toBeVisible();
    // Other action types should not be in the table
    await expect(table.getByText("api key updated")).not.toBeVisible();
  });

  test("clear filter shows all entries", async ({ page }) => {
    await page.goto("/audit");
    const table = page.locator("table");
    // Apply filter
    await page.getByTestId("audit-filter-backend_templates_updated").click();
    await expect(table.getByText("api key updated")).not.toBeVisible();

    // Clear filter
    await page.getByTestId("audit-filter-all").click();
    await expect(table.getByText("api key updated")).toBeVisible();
  });

  test("CR ID links to CR detail page", async ({ page }) => {
    await page.goto("/audit");
    await page.getByText("CR-demo-001").first().click();
    await expect(page).toHaveURL(/\/cr\/CR-demo-001/);
  });
});

// ---------------------------------------------------------------------------
// CR List Search & Filters
// ---------------------------------------------------------------------------

test.describe("CR List Search & Filters", () => {
  test("search bar filters by title", async ({ page }) => {
    await page.goto("/");
    // Should show multiple CRs initially
    await expect(page.getByText("5 runs")).toBeVisible();

    // Search for "auth"
    await page.getByTestId("cr-search").fill("auth");
    // Wait for debounce + results
    await expect(page.getByTestId("cr-card-CR-demo-001")).toBeVisible();
    await expect(page.getByTestId("cr-card-CR-demo-004")).toBeVisible();
    await expect(page.getByTestId("cr-card-CR-demo-002")).not.toBeVisible();
  });

  test("status filter chips filter by status", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("5 runs")).toBeVisible();

    await page.getByTestId("status-filter-failed").click();
    // Only failed CR should be visible
    await expect(page.getByTestId("cr-card-CR-demo-003")).toBeVisible();
    await expect(page.getByTestId("cr-card-CR-demo-002")).not.toBeVisible();
  });

  test("multiple status filters combine", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("status-filter-running").click();
    await page.getByTestId("status-filter-paused").click();

    await expect(page.getByTestId("cr-card-CR-demo-002")).toBeVisible();
    await expect(page.getByTestId("cr-card-CR-demo-004")).toBeVisible();
    await expect(page.getByTestId("cr-card-CR-demo-003")).not.toBeVisible();
  });

  test("sort by highest cost", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("cr-sort").selectOption("cost");

    // First CR card should be the most expensive one (CR-demo-003 at $10.12)
    const cards = page.locator("[data-testid^='cr-card-']");
    await expect(cards.first()).toContainText("Add dark mode support");
  });

  test("empty state with filters shows helpful message", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("cr-search").fill("zzz-nonexistent-query");
    await expect(page.getByText("No pipeline runs found")).toBeVisible();
    await expect(page.getByText("Try adjusting")).toBeVisible();
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
