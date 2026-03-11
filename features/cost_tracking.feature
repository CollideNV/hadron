Feature: Cost Tracking
  The pipeline tracks token usage and USD cost for every agent
  invocation and accumulates totals across the entire CR run.

  Scenario: Track cost per agent invocation
    When an agent completes execution
    Then the input token count is recorded
    And the output token count is recorded
    And the USD cost is calculated using model-specific pricing

  Scenario: Accumulate cost across stages
    Given multiple agents execute across different pipeline stages
    When each agent completes
    Then cost_input_tokens, cost_output_tokens, and cost_usd are accumulated via state reducers
    And the running total reflects all agent invocations

  Scenario: Store final cost in database
    When the pipeline completes
    Then the total cost_usd is stored in the CRRun record

  Scenario: Include cost in events
    When an agent completes
    Then a COST_UPDATE event is emitted with the incremental token counts and cost

  Scenario: Model visibility in events
    When an agent starts and completes
    Then the agent_started event includes the model name
    And the agent_completed event includes the model name
    And the dashboard displays the model as a badge on each agent session

  Scenario: Throttle cost tracked alongside token cost
    Given an agent is rate-limited during execution
    When the agent completes
    Then throttle_count and throttle_seconds are included in the agent_completed event
    And throttle_count and throttle_seconds accumulate in the pipeline state via reducers
    And the dashboard shows time lost to throttling per session and in the footer

  Scenario: Per-model cost and throttle breakdown
    Given an agent uses multiple models across phases (e.g. Haiku for explore, Sonnet for act)
    When the agent completes
    Then the AgentResult includes a model_breakdown dict keyed by model name
    And each entry contains input_tokens, output_tokens, cost_usd, throttle_count, throttle_seconds
    And model_breakdown is included in the agent_completed event
    And model_breakdown accumulates in the pipeline state via a merge reducer
    And the dashboard footer shows a per-model row with tokens, cost, and throttle time
