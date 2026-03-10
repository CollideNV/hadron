Feature: Repo Identification
  The repo identification stage determines which repositories are
  affected by the change request. In the MVP the Controller reads
  repo URLs directly from the intake request and spawns one worker
  per repo.

  Scenario: Identify repos from intake request
    Given a CR has been triggered with one or more repo URLs
    When the Controller processes the CR
    Then one worker is spawned per repo URL
    And each worker receives its repo_url and default_branch

  Scenario: Reject CR with no repos specified
    Given a CR has been triggered with no repo URLs
    When the Controller processes the CR
    Then the CR is rejected with an error indicating no repos were specified
