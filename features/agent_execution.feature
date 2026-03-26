Feature: Agent Execution
  Agents execute tasks via a tool-use loop, with file system and
  command execution tools confined to the working directory. Rate
  limiting is handled with automatic retry and backoff.

  # --- Tool-use loop ---

  Scenario: Execute agent with tool-use loop
    Given an agent task with a system prompt and user prompt
    When the agent is invoked
    Then it enters a tool-use loop processing tool calls until the model stops
    And each tool call is executed and the result fed back to the model
    And the final text response is returned as the agent output

  Scenario: Available agent tools
    Given an agent is executing in a repo worktree
    Then it can read files, write files, delete files, and list directories
    And it can execute shell commands within the worktree

  Scenario: File tools are confined to the working directory
    Given an agent is executing in a working directory
    When a tool receives a path that escapes the working directory
    Then the tool returns a confinement error and the file system is not accessed
    When a tool path resolves through a symlink to outside the working directory
    Then the tool returns a symlink confinement error
    When a path resolves back inside the working directory after traversal
    Then the tool allows the operation

  Scenario: Command timeout
    Given an agent executes a shell command
    When the command exceeds the timeout
    Then the process is killed and the tool returns a timeout error

  # --- Rate limiting ---

  Scenario: Transient error retry with server-guided backoff
    Given the AI provider returns a transient error (rate limit, 500, 503, or 529)
    When the response includes a retry-after hint
    Then the agent waits for the server-specified duration
    When no retry-after hint is provided
    Then it falls back to linear backoff
    And it retries up to the maximum number of attempts before failing
