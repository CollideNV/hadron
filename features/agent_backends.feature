Feature: Agent Backends
  Multiple AI backends are supported and can be configured per stage
  and phase. Backends are cached and reused across stages.

  Scenario: Select agent backend per stage and phase
    Given stage model settings assign different backends to different stages
    When a stage executes its agent
    Then the agent uses the backend and model configured for that stage and phase
    And if no per-stage override exists it falls back to the default backend

  Scenario: Backend pool caches and reuses backends
    Given multiple stages use the same backend
    When each stage requests that backend from the pool
    Then the same backend instance is returned without re-creation

  Scenario: Named OpenCode endpoint as backend
    Given an OpenCode endpoint "local-ollama" is configured with a base URL and models
    When a stage is configured to use backend "opencode:local-ollama"
    Then the agent connects to that endpoint's base URL
    And the endpoint's model list is available for selection

  Scenario: Plain OpenCode backend with free-text model
    Given no named OpenCode endpoints are configured
    When a stage uses the "opencode" backend
    Then the agent connects to the global OpenCode base URL from environment
    And any model name can be entered as free text

  Scenario: Unknown backend name is rejected
    When a stage references an unrecognised backend name
    Then backend creation fails with a descriptive error
