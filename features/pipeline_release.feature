Feature: Release Gate and Release
  The release gate is a Controller-level concern. Workers push PRs
  and terminate. The Controller waits for all repos in a CR to have
  reviewed PRs, then presents a unified release gate to the human.

  Scenario: Worker pushes PR and terminates
    Given the review stage has passed and rebase is clean
    When the worker completes delivery
    Then it pushes the feature branch and opens a PR
    And the worker terminates

  Scenario: Controller tracks worker completion
    Given a CR affects 3 repos
    When each worker pushes its PR and terminates
    Then the Controller tracks completion: 1/3, 2/3, 3/3

  Scenario: Unified release gate when all repos ready
    Given all workers for a CR have pushed their PRs
    When the Controller detects all repos are ready
    Then it presents a unified release summary to the human
    And the summary includes per-repo specs, diffs, test results, review findings, and total cost

  Scenario: Auto-approve at release gate in MVP
    Given all workers for a CR have pushed their PRs
    When the release gate executes in MVP mode
    Then it auto-approves the release
    And the Controller merges all PRs

  Scenario: Human approves release
    Given all workers for a CR have pushed their PRs
    And the release gate is presented to the human
    When the human approves
    Then the Controller merges all PRs across all repos

  Scenario: Partial completion blocks release gate
    Given a CR affects 3 repos
    And 2 workers have completed but 1 is still running
    Then the release gate does not open
    And the dashboard shows per-repo status

  Scenario: Failed worker blocks release gate
    Given a CR affects 3 repos
    And 2 workers have completed but 1 has paused with a circuit breaker
    Then the release gate does not open
    And the human can act on the failed repo without affecting successful ones

  Scenario: Stale approval triggers re-rebase
    Given the human has approved the release
    But main has moved since the last rebase for one repo
    When the Controller performs the atomic merge check
    Then it spawns a new worker for the stale repo to rebase and re-test
    And the human does not need to re-approve unless tests fail
