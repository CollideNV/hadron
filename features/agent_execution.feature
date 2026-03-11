Feature: Agent Execution
  Agents use the Anthropic Claude API in a manual tool-use loop.
  They have access to file system and command execution tools,
  with rate limiting and cost tracking.

  Scenario: Execute agent with tool-use loop
    Given an agent task with a system prompt and user prompt
    When the agent backend invokes the Claude API
    Then it enters a tool-use loop processing tool calls until the model stops
    And each tool call is executed and the result fed back to the model
    And the final text response is returned as the agent output

  Scenario: Agent uses file system tools
    When an agent needs to interact with the codebase
    Then it can use read_file to read file contents
    And it can use write_file to write or create files
    And it can use list_directory to explore the directory structure
    And it can use run_command to execute shell commands

  Scenario: File tools are confined to the working directory
    Given an agent is executing in a working directory
    When a tool receives a path containing "../" that escapes the working directory
    Then the tool returns an error "Path escapes working directory"
    And the file system is not accessed
    When a tool receives an absolute path outside the working directory
    Then the tool returns the same confinement error
    When a tool path resolves through a symlink to a location outside the working directory
    Then the tool returns the same confinement error
    When a path like "subdir/../file.txt" resolves back inside the working directory
    Then the tool allows the operation

  Scenario: Command timeout kills the process
    Given an agent executes a run_command tool call
    When the command exceeds the 120-second timeout
    Then the process is killed
    And the tool returns a timeout error
    And no zombie process is left behind

  Scenario: Rate limit retry with server-guided backoff
    Given the Claude API returns a rate limit error
    When the response includes a Retry-After header
    Then the agent waits for the server-specified duration (clamped to 2s–120s)
    When the response has no Retry-After header
    Then it falls back to exponential backoff starting at 10 seconds
    And it retries up to 8 times before failing
    And the retry count and total wait time are recorded in the result

  Scenario: Throttle tracking across phases
    Given an agent task with three phases configured
    When rate limiting occurs during the explore and act phases
    Then throttle_count and throttle_seconds are accumulated across all phases
    And the totals are included in the AgentResult
    And a throttle summary is emitted in the agent_completed event

  Scenario: Track agent cost
    When an agent completes execution
    Then the input token count, output token count, and USD cost are recorded
    And the model used is recorded in the result
    And the cost is accumulated in the pipeline state via reducers

  Scenario: Track throttle time in pipeline state
    Given multiple agents execute across different pipeline stages
    When rate limiting causes retries
    Then throttle_count and throttle_seconds are accumulated in the pipeline state via reducers
    And the dashboard displays total time lost to throttling per agent session

  Scenario: Store agent conversation
    When an agent completes execution
    Then the full conversation is serialized and stored in Redis
    And the conversation has a 7-day TTL
    And it can be retrieved via the conversation API endpoint

  Scenario: Compose agent prompts in four layers
    When an agent prompt is composed
    Then Layer 1 is the role system prompt from the template file
    And Layer 2 is the repo context including AGENTS.md, language, and directory tree
    And Layer 3 is the task payload with CR details, specs, and code
    And Layer 4 is loop feedback from previous stages
    And the static context is capped at approximately 12k tokens
