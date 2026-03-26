Feature: Budget Enforcement
  The pipeline enforces a configurable cost budget. When exceeded, the
  pipeline pauses with a clear reason. Multiple pause reasons are
  supported, each inferred from the pipeline state.

  # --- Budget checks ---

  Scenario: Pipeline pauses when cost budget is exceeded
    Given a max_cost_usd of 10.0 is configured
    And the pipeline has accumulated $10.00 or more in cost
    When any conditional edge evaluates after an agent call
    Then the pipeline routes to the paused node
    And this applies to verification, implementation, rework, and review edges

  Scenario: Budget defaults to $10 when not configured
    Given no max_cost_usd is set in the config snapshot
    When the budget check runs
    Then the default limit of $10.00 is used

  Scenario: Under-budget pipeline continues normally
    Given a max_cost_usd of 10.0 is configured
    And the pipeline has accumulated $5.00 in cost
    When a conditional edge evaluates
    Then the pipeline routes based on normal logic (not paused)

  # --- Pause reasons ---

  Scenario: Paused node infers and records pause reason
    When the pipeline routes to the paused node
    Then the pause_reason field is set in the pipeline state
    And a pipeline_paused event is emitted with the reason

  Scenario: Budget exceeded pause reason
    Given the pipeline cost has exceeded max_cost_usd
    When the paused node executes
    Then the pause_reason is "budget_exceeded"

  Scenario: Circuit breaker pause reason
    Given a loop count has reached its configured maximum
    When the paused node executes
    Then the pause_reason is "circuit_breaker"

  Scenario: Rebase conflict pause reason
    Given the rebase resulted in unresolvable conflicts
    When the paused node executes
    Then the pause_reason is "rebase_conflict"

  Scenario: Error pause reason
    Given a pipeline node raised an unhandled exception
    When the paused node executes
    Then the pause_reason is "error"
    And the error field contains the exception message
