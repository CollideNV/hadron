Feature: Three-phase agent execution
  Agents execute in up to three phases — Explore, Plan, Act — each using a
  different model optimised for its task. This spreads load across rate-limit
  pools, reduces cost, and improves output quality.

  Scenario: Code writer uses explore-plan-act
    Given a code_writer agent task with explore_model and plan_model configured
    When the agent backend executes the task
    Then phase 1 (Explore) runs with the explore model and read-only tools
    And phase 2 (Plan) runs with the plan model in a single API call with no tools
    And phase 3 (Act) runs with the default model and all tools
    And the act phase receives the plan and exploration summary in its user prompt
    And costs are aggregated across all three phases

  Scenario: Reviewer uses explore-only
    Given a security_reviewer agent task with explore_model configured but no plan_model
    When the agent backend executes the task
    Then phase 1 (Explore) runs with the explore model
    And the plan phase is skipped
    And the act phase uses the explore model since reviewers only read and output JSON

  Scenario: Phases skipped when models not configured
    Given an agent task with empty explore_model and empty plan_model
    When the agent backend executes the task
    Then no explore or plan phases run
    And the act phase runs identically to the original single-phase behaviour
    And the user prompt is passed through unchanged

  Scenario: Exploration summary passed to planner
    Given a completed explore phase with a summary of the codebase
    When the plan phase runs
    Then the planner receives the exploration summary and the original task
    And the planner's system prompt includes the original role instructions

  Scenario: Plan passed to act phase
    Given a completed plan phase with an implementation plan
    When the act phase runs
    Then the act phase user prompt includes the implementation plan
    And the act phase user prompt includes the exploration summary
    And the original task is included after the plan

  Scenario: Phase events are emitted
    Given an agent task with all three phases configured
    When the agent backend executes the task
    Then a phase_started event is emitted before each phase
    And a phase_completed event is emitted after each phase
    And each event includes the phase name and model used

  Scenario: Per-model cost calculation
    When computing costs for a multi-phase execution
    Then Haiku tokens are priced at $0.80/$4.00 per million
    And Sonnet tokens are priced at $3.00/$15.00 per million
    And Opus tokens are priced at $15.00/$75.00 per million
    And the total cost is the sum across all phases

  Scenario: Per-model breakdown in result
    Given an agent uses Haiku for explore and Sonnet for act
    When the agent completes
    Then model_breakdown contains an entry for each model used
    And each entry has input_tokens, output_tokens, cost_usd, throttle_count, throttle_seconds
    And the sum of all entries equals the aggregate totals in AgentResult
    And the breakdown is included in the agent_completed event

  Scenario: Per-model breakdown accumulated in pipeline state
    Given multiple agents execute using different models
    When model_breakdown dicts are returned from pipeline nodes
    Then the merge_model_breakdowns reducer merges them by model name
    And the pipeline-level breakdown shows total usage per model across all stages
    And the dashboard displays a per-model cost and throttle summary

  Scenario: Model name recorded in result
    When an agent completes a multi-phase execution
    Then the AgentResult includes the act-phase model name
    And the agent_completed event includes the model name
    And the dashboard shows the model as a badge next to the agent role

  Scenario: Throttle stats accumulated across phases
    Given rate limiting occurs during the explore phase and the act phase
    When the agent completes
    Then throttle_count is the sum of retries across all phases
    And throttle_seconds is the total wait time across all phases
    And both values are included in the AgentResult
