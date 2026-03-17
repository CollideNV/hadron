Feature: Release Gate
  The release gate is a Controller-level concern. Workers push PRs
  and terminate. The Controller waits for all repos in a CR to have
  reviewed PRs, then presents a unified release gate to the human.

  Scenario: Worker pushes PR and terminates
    Given the review stage has passed and rebase is clean
    When the worker completes delivery
    Then it pushes the feature branch and generates a PR description
    And the worker terminates

  Scenario: Controller tracks worker completion
    Given a CR affects 3 repos
    When each worker pushes its PR and terminates
    Then the Controller tracks completion progress

  Scenario: Unified release gate when all repos ready
    Given all workers for a CR have pushed their PRs
    When the Controller detects all repos are ready
    Then it presents a unified release summary to the human
    And the summary includes per-repo specs, diffs, test results, review findings, and total cost

  Scenario: Human approves release
    Given all workers for a CR have pushed their PRs
    And the release gate is presented to the human
    When the human approves
    Then the CR status is updated to completed
    And a pipeline completed event is emitted

  Scenario: Partial completion blocks release gate
    Given a CR affects 3 repos
    And not all workers have completed
    Then the release gate does not open
    And the dashboard shows per-repo status

  Scenario: Failed worker blocks release gate
    Given a CR affects multiple repos
    And one worker has paused with a circuit breaker
    Then the release gate does not open
    And the human can act on the failed repo without affecting successful ones

  Scenario: Approve rejects when repos are not all completed
    Given a CR affects multiple repos
    And not all repo workers have completed
    When the human attempts to approve
    Then the request is rejected with details of which repos are not ready
