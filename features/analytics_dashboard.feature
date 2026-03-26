Feature: Analytics Dashboard
  The analytics page provides aggregate pipeline metrics including
  success rates, stage durations, cost breakdowns, and daily trends.

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
