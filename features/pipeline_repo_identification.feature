Feature: Repo Identification
  The repo identification stage determines which repositories are
  affected by the change request. In the MVP this reads repos
  directly from the intake request rather than using landscape
  intelligence.

  Scenario: Identify repos from intake request
    Given a CR has completed intake with a repo URL specified
    When the repo identification node executes
    Then a RepoContext is created for each specified repo
    And each RepoContext contains repo_url, repo_name, and default_branch

  Scenario: Reject CR with no repos specified
    Given a CR has completed intake with no repo URL
    When the repo identification node executes
    Then the pipeline fails with an error indicating no repos were specified
