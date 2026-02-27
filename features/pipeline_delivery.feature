Feature: Delivery
  The delivery stage runs the full test suite and pushes the
  feature branch. The MVP uses the self_contained delivery strategy.

  Scenario: Deliver successfully after tests pass
    Given the rebase completed cleanly
    When the delivery node runs the full test suite
    And all tests pass
    Then the changes are committed and pushed to the feature branch
    And the delivery result is marked as delivered

  Scenario: Delivery fails when tests fail
    Given the rebase completed cleanly
    When the delivery node runs the full test suite
    And tests fail
    Then the delivery result is marked as not delivered
    And the test failure output is recorded
