Feature: Analytics Dashboard
  The analytics page provides aggregate pipeline metrics including
  success rates, stage durations, cost breakdowns, and daily trends.
  The CR detail page includes a cost breakdown modal for per-run costs.

  # --- Analytics page ---

  Scenario: Navigate to the analytics page
    Given the user is on the pipelines page
    When the user clicks "Analytics" in the top navigation
    Then the analytics page loads at /analytics
    And the page title is "Analytics"

  Scenario: Display KPI summary cards
    Given the analytics page is loaded
    Then four KPI cards are visible: Total Runs, Success Rate, Total Cost, Avg Cost / Run
    And each card shows a numeric value

  Scenario: Status distribution chart
    Given CRs exist with different statuses (completed, running, failed, paused, pending)
    When the analytics page is loaded
    Then a donut chart shows the status distribution
    And a legend lists each status with its count

  Scenario: Daily run trend chart (pending — backend stub)
    # The /analytics/summary endpoint returns daily_stats as an empty list.
    # The frontend shows an empty area chart until this is implemented.
    Given the analytics page is loaded
    Then the daily trend area chart is visible
    And it displays an empty state when no daily stats are available

  Scenario: Average stage duration chart (pending — backend stub)
    # The /analytics/summary endpoint returns stage_durations as an empty list.
    # The frontend shows an empty bar chart until this is implemented.
    Given the analytics page is loaded
    Then the stage duration bar chart is visible
    And it displays an empty state when no stage duration data is available

  Scenario: Cost breakdown by stage (pending — backend stub)
    # The /analytics/cost?group_by=stage endpoint returns an empty groups list.
    Given the analytics page is loaded
    And the "Stage" cost tab is selected
    Then the cost chart is visible with no data

  Scenario: Cost breakdown by model (pending — backend stub)
    # The /analytics/cost?group_by=model endpoint returns an empty groups list.
    When the user selects the "Model" cost tab
    Then the cost chart is visible with no data

  Scenario: Cost breakdown by repo
    Given CRs have run against multiple repositories
    When the user selects the "Repo" cost tab
    Then the bar chart updates to show cost per repo

  Scenario: Cost breakdown over time (pending — backend stub)
    # The /analytics/cost?group_by=day endpoint returns an empty groups list.
    When the user selects the "Daily" cost tab
    Then the cost chart is visible with no data

  # --- CR detail cost modal ---

  Scenario: Open the cost dashboard from the header
    Given the user is viewing a CR detail page
    When the user clicks the cost tracker in the header
    Then a cost breakdown modal opens
    And the modal title is "Cost Breakdown"

  Scenario: Close the cost dashboard
    Given the cost breakdown modal is open
    When the user presses the Escape key or clicks outside the modal
    Then the modal closes

  Scenario: Display total pipeline cost
    Given agents have completed execution for the current CR
    When the cost breakdown modal is open
    Then the total pipeline cost is displayed prominently

  Scenario: Per-run cost breakdown by stage
    Given agents have completed across multiple stages
    When the cost breakdown modal is open
    Then a table shows each stage with its agent count, tokens, and cost
    And stages are sorted by cost descending
    And each row includes a proportional bar showing its share of the total

  Scenario: Sub-stages are grouped under their parent stage
    Given agents have completed in sub-stages like review:security_reviewer
    When the cost breakdown modal is open
    Then sub-stage costs are grouped under the parent stage (e.g. "review")

  Scenario: Per-run cost breakdown by model
    Given agents have reported per-model breakdowns
    When the cost breakdown modal is open
    Then a table shows each model with its API call count, tokens, and cost
    And models are sorted by cost descending

  Scenario: Model fallback when no breakdown is available
    Given an agent completed event has a model but no model_breakdown
    When the cost breakdown modal is open
    Then the agent's cost is attributed to its single reported model

  Scenario: Cost over time sparkline
    Given at least two agents have completed at different timestamps
    When the cost breakdown modal is open
    Then a sparkline chart shows cumulative cost over time

  Scenario: Empty state when no cost data exists
    Given no agents have completed for the current CR
    When the user clicks the cost tracker
    Then the modal shows an informational message that costs appear as agents complete work
