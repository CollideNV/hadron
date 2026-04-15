Feature: Release Gate
  The release gate is a Controller-level concern. Workers create PRs
  on GitHub and terminate. The Controller waits for all repos in a CR
  to have reviewed PRs, then presents a unified release gate to the
  human. Approval triggers PR merging only if all PRs have GitHub
  review approvals.

  # --- Worker-side PR creation ---

  Scenario: Worker creates PR on GitHub and terminates
    Given the review stage has passed and rebase is clean
    When the worker completes delivery and the release node runs
    Then it pushes the feature branch
    And creates a pull request on GitHub with the generated PR description
    And the pr_url is persisted to the database
    And the worker terminates

  Scenario: PR creation failure does not crash the pipeline
    Given the release node runs
    And the GitHub API is unreachable or returns an error
    Then a warning is logged
    And the pr_url is left empty
    And the worker terminates normally

  Scenario: PR already exists for the branch
    Given the release node runs
    And a pull request already exists for the feature branch
    Then the existing PR is reused
    And its URL is persisted as the pr_url

  # --- Controller-side release gate ---

  Scenario: Controller tracks worker completion
    Given a CR affects 3 repos
    When each worker creates its PR and terminates
    Then the Controller tracks completion progress

  Scenario: Unified release gate when all repos ready
    Given all workers for a CR have created their PRs
    When the Controller detects all repos are ready
    Then it presents a unified release summary to the human
    And the summary includes per-repo specs, diffs, test results, review findings, and total cost

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

  # --- Approval checking and merging ---

  Scenario: Human approves release with all PRs approved
    Given all workers for a CR have created their PRs
    And every PR has at least one GitHub review approval
    When the human approves the release
    Then each PR is merged via the GitHub API
    And the CR status is updated to completed
    And a pipeline completed event is emitted

  Scenario: Approve rejects when PRs lack GitHub review approvals
    Given all workers for a CR have created their PRs
    And one or more PRs have not been approved on GitHub
    When the human attempts to approve the release
    Then the request is rejected with a 409 status
    And the response lists which PRs are not yet approved
    And no PRs are merged

  Scenario: Merge conflict during release approval
    Given all PRs are approved on GitHub
    When the human approves and a merge conflict occurs on one repo
    Then the request is rejected with details of which repo failed
    And no CR status change occurs

  Scenario: Repos without PR URLs are skipped during merge
    Given a repo worker completed but PR creation had failed
    And the repo has no pr_url in the database
    When the human approves the release
    Then that repo is skipped during merging
    And the response lists it under repos_skipped
