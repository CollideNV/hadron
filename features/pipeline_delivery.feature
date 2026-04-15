Feature: Delivery
  The delivery stage dispatches to the configured delivery strategy,
  which determines how changes reach the target repository and whether
  the pipeline waits for external CI before proceeding to release.

  # --- self_contained (default) ---

  Scenario: Self-contained delivery succeeds after tests pass
    Given the rebase completed cleanly
    And the delivery strategy is "self_contained"
    When the delivery stage runs the full test suite
    And all tests pass
    Then the changes are committed and pushed to the feature branch
    And the pipeline proceeds to the release stage

  Scenario: Self-contained delivery fails when tests fail
    Given the rebase completed cleanly
    And the delivery strategy is "self_contained"
    When the delivery stage runs the full test suite
    And tests fail
    Then the delivery result is marked as not delivered
    And the test failure output is recorded
    And the pipeline still proceeds unconditionally to the release stage

  # --- push_and_wait ---

  Scenario: Push-and-wait pushes branch and pauses for CI callback
    Given the rebase completed cleanly
    And the delivery strategy is "push_and_wait"
    When the delivery stage executes
    Then the changes are committed and pushed to the feature branch
    And the pipeline pauses with reason "waiting_for_ci"
    And the worker terminates and checkpoints state

  Scenario: Push-and-wait resumes after CI callback
    Given the pipeline is paused with reason "waiting_for_ci"
    When the controller receives a CI result via POST /pipeline/{cr_id}/ci-result
    Then the worker is resumed from the checkpoint
    And the pipeline proceeds to the release stage

  # --- push_and_forget ---

  Scenario: Push-and-forget pushes branch and proceeds immediately
    Given the rebase completed cleanly
    And the delivery strategy is "push_and_forget"
    When the delivery stage executes
    Then the changes are committed and pushed to the feature branch
    And the delivery result is marked as delivered
    And the pipeline proceeds to the release stage without waiting for CI

  # --- PR creation (always in release stage, not delivery) ---

  Scenario: PR description generated and PR created in release stage
    When the release stage executes after a successful delivery
    Then it generates a PR description including the CR title, acceptance criteria, and pipeline stats
    And the description includes review findings and cost
    And a pull request is created on GitHub with this description
    And the pr_url is stored in the database for use by the release gate
