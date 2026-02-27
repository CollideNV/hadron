Feature: Worktree Setup
  The worktree setup stage clones repositories as bare clones and
  creates isolated git worktrees for the CR's feature branch.

  Scenario: Clone and create worktree for a new repo
    Given a CR with an identified repo that has not been cloned before
    When the worktree setup node executes
    Then the repo is cloned as a bare clone into the workspace
    And a worktree is created at "runs/cr-{cr_id}/{repo_name}/"
    And a feature branch "ai/cr-{cr_id}" is created from the default branch

  Scenario: Reuse existing bare clone
    Given a repo has already been bare-cloned in the workspace
    When the worktree setup node executes for a new CR targeting that repo
    Then the existing bare clone is fetched instead of re-cloned
    And a new worktree and feature branch are created for this CR

  Scenario: Read AGENTS.md from repo
    Given a repo contains an AGENTS.md file in its root
    When the worktree setup node executes
    Then the contents of AGENTS.md are stored in the RepoContext
    And this context is available to all subsequent agent prompts

  Scenario: Read CLAUDE.md as fallback
    Given a repo contains a CLAUDE.md but no AGENTS.md
    When the worktree setup node executes
    Then the contents of CLAUDE.md are stored in the RepoContext

  Scenario: Capture directory tree for context
    When the worktree setup node completes
    Then a directory tree of the repo is captured at 3 levels depth
    And hidden directories and common noise directories are excluded
