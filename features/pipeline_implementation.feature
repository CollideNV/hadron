Feature: Implementation
  The implementation stage uses a single agent with explore-plan-act
  phases to write tests, implement code, and verify all tests pass.

  Scenario: Initial implementation
    Given behaviour specs have been verified
    When the implementation stage runs for the first time
    Then a single implementation agent is invoked with CR, feature specs, and repo context
    And the agent writes tests and implementation code
    And the test suite is executed to verify the result

  Scenario: Commit after implementation
    Given the implementation agent has completed
    When the test suite result is recorded
    Then the changes are committed to the feature branch

  Scenario: Post-review rework uses a dedicated rework node
    Given the review stage has rejected the code with findings
    When the rework node executes
    Then it uses the implementation_rework role and prompt template
    And it skips explore and plan phases (act only)
    And it receives only the CR title and review findings as payload
    And it runs tests and commits after applying fixes

  Scenario: Review feedback included in rework prompt
    Given the review stage produced security and quality findings
    When the rework node is invoked
    Then the findings are included in the agent prompt with severity, message, file, and line
