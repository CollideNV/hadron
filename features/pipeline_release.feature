Feature: Release Gate and Release
  The release gate provides a point for human approval before
  release. In the MVP it auto-approves. The release stage generates
  a PR description but does not yet create an actual PR.

  Scenario: Auto-approve at release gate in MVP
    Given delivery has completed successfully
    When the release gate node executes
    Then it auto-approves the release
    And the pipeline proceeds to the release stage

  Scenario: Generate PR description
    Given the release gate has approved
    When the release node executes
    Then it ensures the feature branch is pushed
    And it generates a PR description from the CR, acceptance criteria, review findings, and pipeline stats
    And the pipeline stats include dev loop count, review loop count, and total cost

  Scenario: Record release results
    When the release node completes
    Then the release results are stored in the pipeline state
    And the pipeline proceeds to the retrospective
