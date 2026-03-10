Feature: Delivery
  The delivery stage runs the full test suite, pushes the feature
  branch, and opens a PR. The worker then terminates. The Controller
  handles release coordination across repos.

  Scenario: Deliver successfully after tests pass
    Given the rebase completed cleanly
    When the delivery node runs the full test suite
    And all tests pass
    Then the changes are committed and pushed to the feature branch
    And a PR is opened with a structured description
    And the worker terminates

  Scenario: Delivery fails when tests fail
    Given the rebase completed cleanly
    When the delivery node runs the full test suite
    And tests fail
    Then the delivery result is marked as not delivered
    And the test failure output is recorded
    And the pipeline loops back to TDD or pauses

  Scenario: PR description includes pipeline context
    When the delivery node opens a PR
    Then the PR body includes the CR title, acceptance criteria, and source link
    And the PR body includes test results, review findings, and cost
    And for multi-repo CRs, the PR links to sibling PRs in other repos
