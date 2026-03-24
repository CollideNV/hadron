Feature: Cost Dashboard
  The cost tracker in the CR detail header opens a modal dashboard
  showing per-stage costs, per-model costs, and a cost-over-time
  sparkline. All data is derived from agent_completed events.

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

  Scenario: Cost breakdown by stage
    Given agents have completed across multiple stages
    When the cost breakdown modal is open
    Then a table shows each stage with its agent count, tokens, and cost
    And stages are sorted by cost descending
    And each row includes a proportional bar showing its share of the total

  Scenario: Sub-stages are grouped under their parent stage
    Given agents have completed in sub-stages like review:security_reviewer
    When the cost breakdown modal is open
    Then sub-stage costs are grouped under the parent stage (e.g. "review")

  Scenario: Cost breakdown by model
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
