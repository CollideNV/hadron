Feature: Agent Cost Tracking
  Cost and throttle metrics are tracked per agent invocation and
  accumulated across the pipeline. Per-model breakdowns track
  individual model usage.

  # --- Cost tracking ---

  Scenario: Track cost per agent invocation
    When an agent completes execution
    Then input tokens, output tokens, and cost are recorded
    And the model used is recorded

  Scenario: Accumulate cost across stages
    Given multiple agents execute across different pipeline stages
    When each agent completes
    Then token counts and cost are accumulated in the pipeline state
    And the running total reflects all agent invocations

  Scenario: Per-model cost breakdown
    Given an agent uses different models across phases
    When the agent completes
    Then a per-model breakdown is produced with tokens, cost, and throttle time
    And the breakdown is accumulated across stages in the pipeline state

  Scenario: Store final cost in database
    When the pipeline completes
    Then the total cost is persisted in the run record

  # --- Throttle tracking ---

  Scenario: Throttle time tracked across phases and stages
    Given rate limiting occurs during agent execution
    When the agent completes
    Then retry count and total wait time are recorded
    And throttle metrics are accumulated across phases and pipeline stages

  # --- Conversation storage ---

  Scenario: Store and retrieve agent conversation
    When an agent completes execution
    Then the full conversation is persisted and retrievable via the API
