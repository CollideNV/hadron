Feature: Analytics Dashboard
  The analytics page provides aggregate pipeline metrics including
  success rates, stage durations, cost breakdowns, and daily trends.
  The CR detail page includes a cost breakdown modal for per-run costs.
  Analytics data is sourced from the RunSummary table, which stores
  structured per-run data persisted at pipeline completion.

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

  Scenario: Daily run trend chart
    Given RunSummary records exist across multiple days
    When the analytics page is loaded
    Then the daily trend area chart shows completed vs failed runs per day
    And the chart shows cost trends over time

  Scenario: Average stage duration chart
    Given RunSummary records exist with stage_timings data
    When the analytics page is loaded
    Then the stage duration bar chart shows average and p95 duration per stage

  Scenario: Cost breakdown by stage
    Given RunSummary records exist with stage timing data
    And the "Stage" cost tab is selected
    Then the cost chart shows per-stage cost distribution
    And cost is approximated proportionally by stage duration

  Scenario: Cost breakdown by model
    Given RunSummary records exist with model_breakdown data
    When the user selects the "Model" cost tab
    Then the cost chart shows per-model cost with API call counts and token usage

  Scenario: Cost breakdown by repo
    Given CRs have run against multiple repositories
    When the user selects the "Repo" cost tab
    Then the bar chart updates to show cost per repo

  Scenario: Cost breakdown over time
    Given RunSummary records exist across multiple days
    When the user selects the "Daily" cost tab
    Then the cost chart shows daily cost totals with run counts

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
