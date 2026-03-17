Feature: Worktree Setup
  The worktree setup stage clones the worker's repository, creates
  an isolated feature branch, auto-detects languages and test tooling,
  and captures repo context for subsequent agent prompts.

  # --- Clone and worktree creation ---

  Scenario: Clone and create worktree for a new repo
    Given a worker has started for a repo that has not been cloned before
    When the worktree setup stage executes
    Then the repo is cloned into the workspace
    And an isolated worktree is created for the CR's feature branch

  Scenario: Reuse existing clone
    Given a repo has already been cloned in the workspace
    When the worktree setup stage executes for a new CR targeting that repo
    Then the existing clone is updated instead of re-cloned
    And a new worktree and feature branch are created for this CR

  Scenario: Recover worktree from remote on resume
    Given a worker has been restarted and the worktree does not exist locally
    When the worktree setup stage recovers from remote
    Then it fetches the feature branch from the remote
    And it recreates the worktree from the remote branch state

  # --- Repo context ---

  Scenario: Read AGENTS.md from repo
    Given a repo contains an AGENTS.md file in its root
    When the worktree setup stage executes
    Then the contents of AGENTS.md are stored as repo context
    And this context is available to all subsequent agent prompts

  Scenario: Read CLAUDE.md as fallback
    Given a repo contains a CLAUDE.md but no AGENTS.md
    When the worktree setup stage executes
    Then the contents of CLAUDE.md are stored as repo context

  Scenario: Capture directory tree for context
    When the worktree setup stage completes
    Then a directory tree of the repo is captured at 3 levels depth
    And hidden directories and common noise directories are excluded
    And the directory tree is included in repo context for subsequent agent prompts

  # --- Language and test detection ---

  Scenario Outline: Auto-detect language and test command
    Given the repo contains a <marker_file>
    When the worktree setup stage executes
    Then "<language>" is added to the detected languages
    And "<test_command>" is added to the detected test commands

    Examples:
      | marker_file     | language   | test_command   |
      | pyproject.toml  | python     | pytest         |
      | package.json    | javascript | npm test       |
      | Cargo.toml      | rust       | cargo test     |
      | go.mod          | go         | go test ./...  |

  Scenario: TypeScript detection when tsconfig is present
    Given the repo contains a package.json and a tsconfig.json
    When the worktree setup stage executes
    Then "typescript" is detected instead of "javascript"

  Scenario: Polyglot repo with multiple languages
    Given the repo contains multiple language marker files
    When the worktree setup stage executes
    Then all matching languages and test commands are detected

  Scenario: AGENTS.md overrides auto-detected test command
    Given the repo's AGENTS.md specifies a custom test command
    When the worktree setup stage executes
    Then the AGENTS.md test command takes precedence over auto-detected commands

  # --- Dependency installation ---

  Scenario: Install dependencies during worktree setup
    Given the repo has been cloned and the worktree created
    When the worktree setup stage detects dependency files
    Then it installs Python dependencies via pip if pyproject.toml or requirements.txt are present
    And it installs Node dependencies via npm if package.json is present
