Feature: Behaviour Verification
  The behaviour verification stage runs a Spec Verifier agent that
  checks whether the generated feature files fully cover the CR's
  acceptance criteria. This forms a feedback loop with translation.

  Scenario: Verify specs are complete
    Given behaviour specs have been written to the worktree
    When the behaviour verification stage executes
    Then the Spec Verifier agent reads the feature files from the worktree
    And it evaluates them against the CR's acceptance criteria
    And it returns a verdict with verified status, feedback, missing scenarios, and issues

  Scenario: Specs pass verification
    Given the Spec Verifier returns verified as true
    When the verification routing decision is made
    Then the pipeline proceeds to the implementation stage

  Scenario: Specs fail verification with retries remaining
    Given the Spec Verifier returns verified as false
    And the verification loop count is below the maximum (default 3)
    When the verification routing decision is made
    Then the pipeline routes back to behaviour translation with the feedback
    And the verification loop count is incremented

  Scenario: Specs fail verification with no retries remaining
    Given the Spec Verifier returns verified as false
    And the verification loop count has reached the maximum (default 3)
    When the verification routing decision is made
    Then the pipeline pauses with a circuit breaker

  Scenario: Custom verification loop limit
    Given a custom verification loop limit is configured
    When the verification routing decision is made
    Then the custom limit is used instead of the default 3
