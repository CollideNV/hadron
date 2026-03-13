Feature: Delivery
  The delivery stage runs the full test suite and pushes the feature
  branch. It does not open a PR — PR description generation happens
  in the release node. After delivery, the pipeline proceeds to
  the release node.

  Scenario: Deliver successfully after tests pass
    Given the rebase completed cleanly
    When the delivery node runs the full test suite
    And all tests pass
    Then the changes are committed and pushed to the feature branch
    And the pipeline proceeds to the release node

  Scenario: Delivery fails when tests fail
    Given the rebase completed cleanly
    When the delivery node runs the full test suite
    And tests fail
    Then the delivery result is marked as not delivered
    And the test failure output is recorded

  Scenario: PR description generated in release node
    When the release node executes after a successful delivery
    Then it generates a PR description including the CR title, acceptance criteria, and source link
    And the description includes test results, review findings, and cost
    And for multi-repo CRs, the description links to sibling PRs in other repos
