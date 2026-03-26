Feature: Agent Cost Tracking
  Cost and throttle metrics are tracked per agent invocation and
  accumulated across the pipeline. Per-model breakdowns track
  individual model usage.

  # --- Cost tracking ---

  Scenario: Track cost per agent invocation
    When an agent completes execution
    Then input tokens, output tokens, and cost are recorded
    And the models used are recorded in a per-model breakdown

  Scenario: Accumulate cost across stages
    Given multiple agents execute across different pipeline stages
    When each agent completes
    Then token counts and cost are accumulated in the pipeline state
    And the running total reflects all agent invocations

  Scenario: Per-model cost breakdown
    Given an agent uses different models across phases
    When the agent completes
    Then a per-model breakdown is produced with tokens, cost, throttle time, cache creation tokens, cache read tokens, and API call count
    And the breakdown is accumulated across stages in the pipeline state

  Scenario: Store final cost in database
    When the pipeline completes
    Then the total cost is persisted in the run record

  # --- Budget enforcement ---

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

  # --- Throttle tracking ---

  Scenario: Throttle time tracked across phases and stages
    Given rate limiting occurs during agent execution
    When the agent completes
    Then retry count and total wait time are recorded
    And throttle metrics are accumulated across phases and pipeline stages

  # --- Conversation storage ---

  Scenario: Store and retrieve agent conversation
    When an agent completes execution
    Then the full conversation is stored in Redis with a 7-day TTL and retrievable via the API
