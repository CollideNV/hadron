import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Analytics Page
// ---------------------------------------------------------------------------

test.describe("Analytics Page", () => {
  test("navigates to analytics from nav", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-analytics").click();
    await expect(page).toHaveURL("/analytics");
    await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  });

  test("displays KPI summary cards", async ({ page }) => {
    await page.goto("/analytics");
    const kpis = page.getByTestId("analytics-kpis");
    await expect(kpis).toBeVisible();
    await expect(kpis.getByText("Total Runs")).toBeVisible();
    await expect(kpis.getByText("Success Rate")).toBeVisible();
    await expect(kpis.getByText("Total Cost")).toBeVisible();
    await expect(kpis.getByText("Avg Cost / Run")).toBeVisible();
  });

  test("shows status distribution chart", async ({ page }) => {
    await page.goto("/analytics");
    const chart = page.getByTestId("analytics-status-chart");
    await expect(chart).toBeVisible();
    await expect(chart.getByText("Status Distribution")).toBeVisible();
    // Should show at least some status labels
    await expect(chart.getByText("completed")).toBeVisible();
  });

  test("shows daily trend chart", async ({ page }) => {
    await page.goto("/analytics");
    const chart = page.getByTestId("analytics-trend-chart");
    await expect(chart).toBeVisible();
    await expect(chart.getByText("Daily Runs (14d)")).toBeVisible();
  });

  test("shows stage duration chart", async ({ page }) => {
    await page.goto("/analytics");
    const chart = page.getByTestId("analytics-stage-durations");
    await expect(chart).toBeVisible();
    await expect(chart.getByText("Average Stage Duration")).toBeVisible();
  });

  test("shows cost breakdown with tabs", async ({ page }) => {
    await page.goto("/analytics");
    const section = page.getByTestId("analytics-cost-breakdown");
    await expect(section).toBeVisible();
    await expect(section.getByText("Cost Breakdown")).toBeVisible();

    // All tabs should be visible
    await expect(page.getByTestId("cost-tab-stage")).toBeVisible();
    await expect(page.getByTestId("cost-tab-model")).toBeVisible();
    await expect(page.getByTestId("cost-tab-repo")).toBeVisible();
    await expect(page.getByTestId("cost-tab-day")).toBeVisible();
  });

  test("switching cost tabs loads different data", async ({ page }) => {
    await page.goto("/analytics");

    // Default is stage
    await expect(page.getByTestId("cost-tab-stage")).toHaveClass(/text-accent/);

    // Switch to model
    await page.getByTestId("cost-tab-model").click();
    await expect(page.getByTestId("cost-tab-model")).toHaveClass(/text-accent/);

    // Switch to repo
    await page.getByTestId("cost-tab-repo").click();
    await expect(page.getByTestId("cost-tab-repo")).toHaveClass(/text-accent/);

    // Switch to daily
    await page.getByTestId("cost-tab-day").click();
    await expect(page.getByTestId("cost-tab-day")).toHaveClass(/text-accent/);
  });

  test("cost breakdown shows total cost", async ({ page }) => {
    await page.goto("/analytics");
    const section = page.getByTestId("analytics-cost-breakdown");
    // Should show a dollar amount
    await expect(section.getByText(/\$\d+\.\d+/).first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Live Activity Feed
// ---------------------------------------------------------------------------

test.describe("Live Activity Feed", () => {
  test("activity feed appears on pipelines page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("activity-feed")).toBeVisible();
    await expect(page.getByText("Live Activity")).toBeVisible();
  });

  test("shows active CRs from global stream", async ({ page }) => {
    await page.goto("/");
    // Wait for SSE to deliver cr_status events
    await expect(page.getByTestId("activity-CR-demo-002")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("activity-CR-demo-004")).toBeVisible({ timeout: 10_000 });
  });

  test("shows connection indicator", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("activity-connection")).toBeVisible();
  });

  test("activity row links to CR detail", async ({ page }) => {
    await page.goto("/");
    // Wait for activity items to load
    await expect(page.getByTestId("activity-CR-demo-002")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("activity-CR-demo-002").click();
    await expect(page).toHaveURL(/\/cr\/CR-demo-002/);
  });

  test("activity updates with real-time events", async ({ page }) => {
    await page.goto("/");
    // Initially should show stage from cr_status event
    await expect(page.getByTestId("activity-CR-demo-002")).toBeVisible({ timeout: 10_000 });
    // After a few seconds, events stream in and update the row
    // The stage_entered event sets the stage to "implementation"
    await expect(page.getByTestId("activity-CR-demo-002").getByText("Implementation").first()).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// Navigation updates
// ---------------------------------------------------------------------------

test.describe("Navigation with Analytics", () => {
  test("analytics nav link is present and works", async ({ page }) => {
    await page.goto("/");
    const navLink = page.getByTestId("nav-analytics");
    await expect(navLink).toBeVisible();
    await expect(navLink).toHaveText("Analytics");
    await navLink.click();
    await expect(page).toHaveURL("/analytics");
  });

  test("full navigation cycle includes analytics", async ({ page }) => {
    await page.goto("/analytics");
    await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();

    await page.getByTestId("nav-pipelines").click();
    await expect(page).toHaveURL("/");

    await page.getByTestId("nav-analytics").click();
    await expect(page).toHaveURL("/analytics");
  });
});
