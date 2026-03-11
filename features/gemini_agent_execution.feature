Feature: Gemini Agent Backend
  The pipeline supports Google Gemini models (e.g. gemini-2.5-pro,
  gemini-2.5-flash) as a pluggable agent backend, with the same
  tool-use loop, three-phase execution, cost tracking, and streaming
  as the Claude backend.

  Background:
    Given the pipeline supports multiple agent backend providers
    And each backend implements the AgentBackend protocol (execute + stream)

  # -------------------------------------------------------------------
  # Backend selection & routing
  # -------------------------------------------------------------------

  Scenario: Route to Gemini backend by model name
    Given an agent task with model "gemini-2.5-pro"
    When the agent backend factory creates a backend for the task
    Then a GeminiAgentBackend instance is returned
    And the Anthropic SDK is NOT invoked

  Scenario: Route to Claude backend by model name
    Given an agent task with model "claude-sonnet-4-20250514"
    When the agent backend factory creates a backend for the task
    Then a ClaudeAgentBackend instance is returned

  Scenario: Unknown model prefix raises an error
    Given an agent task with model "unknown-model-v1"
    When the agent backend factory creates a backend for the task
    Then a ValueError is raised indicating the model is not recognised

  # -------------------------------------------------------------------
  # Tool-use loop
  # -------------------------------------------------------------------

  Scenario: Execute agent with tool-use loop via Gemini
    Given a GeminiAgentBackend configured with a valid API key
    And an agent task with a system prompt and user prompt
    When the agent backend invokes the Gemini API
    Then it enters a tool-use loop processing function calls until the model stops
    And each function call is executed and the result fed back to the model
    And the final text response is returned as the agent output

  Scenario: Gemini agent uses the same tool definitions
    When a Gemini agent needs to interact with the codebase
    Then it can use read_file to read file contents
    And it can use write_file to write or create files
    And it can use list_directory to explore the directory structure
    And it can use run_command to execute shell commands
    And the tool definitions are translated to Gemini function declaration format

  Scenario: File tools are confined to the working directory
    Given a Gemini agent is executing in a working directory
    When a tool receives a path containing "../" that escapes the working directory
    Then the tool returns an error "Path escapes working directory"
    And the file system is not accessed

  # -------------------------------------------------------------------
  # Three-phase execution
  # -------------------------------------------------------------------

  Scenario: Gemini three-phase explore-plan-act
    Given a code_writer agent task with explore_model "gemini-2.5-flash" and plan_model "gemini-2.5-pro"
    When the GeminiAgentBackend executes the task
    Then phase 1 (Explore) runs with gemini-2.5-flash and read-only tools
    And phase 2 (Plan) runs with gemini-2.5-pro in a single API call with no tools
    And phase 3 (Act) runs with the default model and all tools
    And costs are aggregated across all three phases

  Scenario: Phases skipped when models not configured
    Given an agent task with empty explore_model and empty plan_model
    When the GeminiAgentBackend executes the task
    Then the act phase runs identically to single-phase behaviour

  # -------------------------------------------------------------------
  # Cost tracking
  # -------------------------------------------------------------------

  Scenario: Gemini model cost calculation
    When computing costs for a Gemini agent invocation
    Then gemini-2.5-pro tokens are priced at $1.25/$10.00 per million (under 200k context)
    And gemini-2.5-flash tokens are priced at $0.30/$2.50 per million (paid tier, under 200k context)
    And gemini-2.5-flash-lite tokens are priced at $0.10/$0.40 per million
    And gemini-3-flash-preview tokens are priced at $0.50/$3.00 per million
    And gemini-3.1-pro-preview tokens are priced at $2.00/$12.00 per million
    And unknown Gemini models fall back to gemini-2.5-flash pricing ($0.30/$2.50)
    And the total cost is the sum across all phases

  Scenario: Cost included in AgentResult
    When a Gemini agent completes execution
    Then the AgentResult includes input_tokens, output_tokens, and cost_usd
    And the cost is computed using Gemini-specific pricing

  # -------------------------------------------------------------------
  # Rate limiting & retry
  # -------------------------------------------------------------------

  Scenario: Rate limit retry with exponential backoff
    Given a Gemini API call that returns a 429 rate-limit error
    When the backend retries with exponential backoff
    Then it retries up to 5 times with increasing wait times
    And if all retries are exhausted, the error is raised

  Scenario: Rate limit event emitted during retry
    Given a rate-limited Gemini API call with an on_event callback
    When the backend retries
    Then an output event is emitted indicating the rate limit wait

  # -------------------------------------------------------------------
  # Streaming
  # -------------------------------------------------------------------

  Scenario: Stream agent events from Gemini
    Given a GeminiAgentBackend configured for streaming
    When the stream method is called with an agent task
    Then it yields text_delta events as text is generated
    And it yields tool_use events when the model calls a function
    And it yields tool_result events after each function executes
    And it yields a done event when the loop completes

  # -------------------------------------------------------------------
  # Provider chain / failover
  # -------------------------------------------------------------------

  Scenario: Gemini as fallback in provider chain
    Given a provider chain configured as [Claude primary, Gemini fallback]
    When the primary Claude provider fails with a transient error
    And retries are exhausted for Claude
    Then the pipeline falls over to the GeminiAgentBackend
    And the same task is re-executed using a Gemini model

  Scenario: Mixed providers across phases
    Given an agent task with explore_model "gemini-2.5-flash" and plan_model "claude-opus-4-20250514"
    When the agent backend factory routes each phase
    Then the explore phase uses the GeminiAgentBackend
    And the plan phase uses the ClaudeAgentBackend
    And costs are correctly aggregated from both providers

  # -------------------------------------------------------------------
  # Configuration
  # -------------------------------------------------------------------

  Scenario: Gemini API key from config
    Given bootstrap config with a google_api_key
    When a GeminiAgentBackend is created
    Then it uses the configured API key
    And the Google GenAI client is initialised with that key

  Scenario: Gemini API key from environment
    Given the GOOGLE_API_KEY environment variable is set
    When a GeminiAgentBackend is created without an explicit key
    Then it reads the API key from the environment variable

  Scenario: Environment scrubbing for Gemini
    When a Gemini agent executes a run_command tool
    Then the GOOGLE_API_KEY is stripped from the subprocess environment
    And all other sensitive keys are stripped as before
