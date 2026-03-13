Feature: Agent Execution
  Agents execute tasks via a tool-use loop, with file system and
  command execution tools confined to the working directory. Agents
  can run in up to three phases (explore, plan, act) to optimise
  for cost and quality. Cost and throttle metrics are tracked per
  invocation and accumulated across the pipeline.

  # --- Tool-use loop ---

  Scenario: Execute agent with tool-use loop
    Given an agent task with a system prompt and user prompt
    When the agent is invoked
    Then it enters a tool-use loop processing tool calls until the model stops
    And each tool call is executed and the result fed back to the model
    And the final text response is returned as the agent output

  Scenario: Available agent tools
    Given an agent is executing in a repo worktree
    Then it can read files, write files, and list directories
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

  Scenario: Rate limit retry with server-guided backoff
    Given the AI provider returns a rate limit error
    When the response includes a retry-after hint
    Then the agent waits for the server-specified duration
    When no retry-after hint is provided
    Then it falls back to linear backoff
    And it retries up to the maximum number of attempts before failing

  # --- Three-phase execution ---

  Scenario: Three-phase execution for code agents
    Given a code-writing agent with explore and plan models configured
    When the agent executes
    Then phase 1 (Explore) runs with read-only tools to survey the codebase
    And phase 2 (Plan) runs with no tools to produce an implementation plan
    And phase 3 (Act) runs with all tools to implement the plan
    And the act phase receives the exploration summary and plan in its prompt

  Scenario: Single-phase execution for reviewers
    Given a reviewer agent with no explore or plan models configured
    When the agent executes
    Then only the act phase runs
    And the prompt is passed through unchanged

  Scenario: Phase events are emitted
    Given an agent with multiple phases configured
    When the agent executes
    Then a phase started event is emitted before each phase
    And a phase completed event is emitted after each phase

  # --- Cost tracking ---

  Scenario: Track cost per agent invocation
    When an agent completes execution
    Then input tokens, output tokens, and cost are recorded
    And the model used is recorded

  Scenario: Accumulate cost across stages
    Given multiple agents execute across different pipeline stages
    When each agent completes
    Then token counts and cost are accumulated in the pipeline state
    And the running total reflects all agent invocations

  Scenario: Per-model cost breakdown
    Given an agent uses different models across phases
    When the agent completes
    Then a per-model breakdown is produced with tokens, cost, and throttle time
    And the breakdown is accumulated across stages in the pipeline state

  Scenario: Store final cost in database
    When the pipeline completes
    Then the total cost is persisted in the run record

  # --- Throttle tracking ---

  Scenario: Throttle time tracked across phases and stages
    Given rate limiting occurs during agent execution
    When the agent completes
    Then retry count and total wait time are recorded
    And throttle metrics are accumulated across phases and pipeline stages

  # --- Conversation storage ---

  Scenario: Store and retrieve agent conversation
    When an agent completes execution
    Then the full conversation is persisted and retrievable via the API

  # --- Prompt composition ---

  Scenario: Compose agent prompts in four layers
    When an agent prompt is composed
    Then Layer 1 is the role system prompt from the template
    And Layer 2 is the repo context including agent instructions, language, and directory tree
    And Layer 3 is the task payload with CR details, specs, and code
    And Layer 4 is loop feedback from previous stages
