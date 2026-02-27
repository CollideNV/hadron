Feature: Git Operations
  The WorktreeManager handles all git operations: bare cloning,
  worktree creation, committing, pushing, rebasing, and conflict
  detection. It supports GITHUB_TOKEN for authentication.

  Scenario: Clone a repo as bare clone
    Given a repo URL is provided
    When the WorktreeManager clones the repo
    Then it creates a bare clone at "repos/{repo_name}/" in the workspace
    And the bare clone contains no working directory

  Scenario: Fetch existing bare clone
    Given a bare clone already exists for a repo
    When the WorktreeManager is asked to clone the same repo
    Then it fetches all branches from the remote instead of re-cloning

  Scenario: Create a feature branch worktree
    Given a bare clone exists for a repo
    When the WorktreeManager creates a worktree for a CR
    Then a branch "ai/cr-{cr_id}" is created from the default branch
    And a worktree is created at "runs/cr-{cr_id}/{repo_name}/"

  Scenario: Commit and push changes
    Given changes have been made in a worktree
    When the WorktreeManager commits and pushes
    Then all changes are staged
    And a commit is created with the provided message
    And the branch is pushed to the remote

  Scenario: Get diff against base branch
    Given changes exist on the feature branch
    When the WorktreeManager gets the diff
    Then it returns a unified diff comparing the feature branch to the base branch

  Scenario: Authenticate with GITHUB_TOKEN
    Given the GITHUB_TOKEN environment variable is set
    When git operations require remote access
    Then the token is used for HTTPS authentication

  Scenario: Recover worktree from remote on resume
    Given a worker has been restarted and the worktree does not exist locally
    When the WorktreeManager recovers from remote
    Then it fetches the feature branch from the remote
    And it recreates the worktree from the remote branch state
