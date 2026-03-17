Feature: Agent Phases
  Agents can run in up to three phases (explore, plan, act) to
  optimise for cost and quality. Code-writing agents use all three
  phases; reviewers use only the act phase.

  Scenario: Three-phase execution for code agents
    Given a code-writing agent with explore and plan models configured
    When the agent executes
    Then phase 1 (Explore) runs with read-only tools to survey the codebase
    And phase 2 (Plan) runs with no tools to produce an implementation plan
    And phase 3 (Act) runs with all tools to implement the plan
    And the act phase receives the exploration summary and plan in its prompt

  Scenario: Single-phase execution for reviewers
    Given a reviewer agent with no explore or plan models configured
    When the agent executes
    Then only the act phase runs
    And the prompt is passed through unchanged

  Scenario: Skip phase when model is empty
    Given a phase has an empty model string
    When the agent executes
    Then that phase is skipped entirely

  Scenario: Phase events are emitted
    Given an agent with multiple phases configured
    When the agent executes
    Then a phase started event is emitted before each phase
    And a phase completed event is emitted after each phase
