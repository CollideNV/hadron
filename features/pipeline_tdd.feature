Feature: TDD Development
  The TDD stage implements a red-green cycle: a Test Writer agent
  writes failing tests, then a Code Writer agent iterates to make
  them pass. An initial test run provides failure context before
  the Code Writer begins.

  Scenario: Write tests in the RED phase
    Given behaviour specs have been verified
    When the TDD stage begins the RED phase
    Then the Test Writer agent is invoked with the CR and acceptance criteria
    And the agent writes test files to the repo worktree

  Scenario: Include review findings on retry from review
    Given the review stage has rejected the code with findings
    When the TDD stage begins the RED phase again
    Then the Test Writer agent receives the review findings in its prompt

  Scenario: Initial test run before GREEN phase
    Given tests have been written in the RED phase
    When the TDD stage begins the GREEN phase
    Then the test suite is executed first to produce initial failure output
    And the Code Writer agent is invoked with the CR summary, feature specs, test files, and failure output

  Scenario: Iterate on failing tests
    Given the Code Writer agent has written implementation code
    When the test suite is executed and tests fail
    And the iteration count is below the maximum (default 5)
    Then the Code Writer agent is invoked again with the test failure output

  Scenario: Custom TDD iteration limit
    Given a custom TDD iteration limit is configured
    When the GREEN phase iterates
    Then the custom limit is used instead of the default 5

  Scenario: Tests pass within iteration limit
    Given the Code Writer agent has written implementation code
    When the test suite is executed and all tests pass
    Then the GREEN phase completes successfully
    And the changes are committed to the feature branch with a "green" status

  Scenario: Tests do not pass within iteration limit
    Given the iteration count has reached the maximum
    And tests are still failing
    When the GREEN phase completes
    Then the changes are committed to the feature branch with a "red" status
    And the pipeline continues with the current state
    And the test results are recorded for the review stage
