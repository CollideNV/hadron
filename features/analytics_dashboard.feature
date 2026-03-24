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

  Scenario: Daily run trend chart
    Given pipeline runs have occurred over the last 14 days
    When the analytics page is loaded
    Then an area chart shows daily completed and failed counts
    And the X axis shows dates

  Scenario: Average stage duration chart
    Given pipeline runs have completed through multiple stages
    When the analytics page is loaded
    Then a horizontal bar chart shows average and p95 durations per stage
    And stages are labelled with human-readable names

  Scenario: Cost breakdown by stage
    Given agents have accumulated costs across stages
    When the analytics page is loaded
    And the "Stage" cost tab is selected
    Then a bar chart shows cost per stage

  Scenario: Cost breakdown by model
    Given agents have used different models
    When the user selects the "Model" cost tab
    Then the bar chart updates to show cost per model

  Scenario: Cost breakdown by repo
    Given CRs have run against multiple repositories
    When the user selects the "Repo" cost tab
    Then the bar chart updates to show cost per repo

  Scenario: Cost breakdown over time
    When the user selects the "Daily" cost tab
    Then the bar chart updates to show daily cost totals
