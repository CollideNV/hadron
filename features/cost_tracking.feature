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
