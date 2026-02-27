Feature: TDD Development
  The TDD stage implements a red-green cycle: a Test Writer agent
  writes failing tests, then a Code Writer agent iterates to make
  them pass.

  Scenario: Write tests in the RED phase
    Given behaviour specs have been verified
    When the TDD node begins the RED phase
    Then the Test Writer agent is invoked with the CR and acceptance criteria
    And the agent writes test files to the repo worktree
    And a STAGE_ENTERED event is emitted for "tdd:test_writer"

  Scenario: Include review findings on retry from review
    Given the review stage has rejected the code with findings
    When the TDD node begins the RED phase again
    Then the Test Writer agent receives the review findings in its prompt

  Scenario: Implement code in the GREEN phase
    Given tests have been written in the RED phase
    When the TDD node begins the GREEN phase
    Then the Code Writer agent is invoked with the CR and test files
    And the agent writes implementation code to the repo worktree

  Scenario: Iterate on failing tests
    Given the Code Writer agent has written implementation code
    When the test suite is executed and tests fail
    And the TDD iteration count is below the maximum of 5
    Then the Code Writer agent is invoked again with the test failure output
    And it attempts to fix the implementation

  Scenario: Tests pass within iteration limit
    Given the Code Writer agent has written implementation code
    When the test suite is executed and all tests pass
    Then the GREEN phase completes successfully
    And the changes are committed and pushed to the feature branch

  Scenario: Tests do not pass within iteration limit
    Given the TDD iteration count has reached the maximum of 5
    And tests are still failing
    When the GREEN phase completes
    Then the pipeline continues with the current state
    And the test results are recorded for the review stage

  Scenario: Emit sub-stage events during TDD
    When the TDD node executes
    Then STAGE_ENTERED and STAGE_COMPLETED events are emitted for "tdd"
    And STAGE_ENTERED and STAGE_COMPLETED events are emitted for "tdd:test_writer"
    And STAGE_ENTERED and STAGE_COMPLETED events are emitted for "tdd:code_writer"
    And TEST_RUN events are emitted after each test execution
