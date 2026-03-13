Feature: Worktree Setup
  The worktree setup stage clones the worker's repository as a bare
  clone and creates an isolated git worktree for the CR's feature
  branch. It also auto-detects languages and test tooling.

  Scenario: Clone and create worktree for a new repo
    Given a worker has started for a repo that has not been cloned before
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
    And the directory tree is stored in the pipeline state
    And it is included in repo context for subsequent agent prompts

  Scenario: Auto-detect Python project
    Given the repo contains a pyproject.toml or setup.py
    When the worktree setup node executes
    Then "python" is added to the detected languages
    And "pytest" is added to the detected test commands

  Scenario: Auto-detect Node.js project
    Given the repo contains a package.json
    When the worktree setup node executes
    Then "javascript" or "typescript" is added to the detected languages
    And "npm test" is added to the detected test commands

  Scenario: Auto-detect Rust project
    Given the repo contains a Cargo.toml
    When the worktree setup node executes
    Then "rust" is added to the detected languages
    And "cargo test" is added to the detected test commands

  Scenario: Auto-detect Go project
    Given the repo contains a go.mod
    When the worktree setup node executes
    Then "go" is added to the detected languages
    And "go test ./..." is added to the detected test commands

  Scenario: Polyglot repo with multiple languages
    Given the repo contains both pyproject.toml and package.json
    When the worktree setup node executes
    Then both "python" and "javascript" are detected as languages
    And both "pytest" and "npm test" are detected as test commands

  Scenario: AGENTS.md overrides auto-detected test command
    Given the repo's AGENTS.md specifies a custom test command
    When the worktree setup node executes
    Then the AGENTS.md test command takes precedence over auto-detected commands
