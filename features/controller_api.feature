Feature: Controller API
  The controller exposes REST endpoints for triggering pipelines,
  listing runs, streaming events, managing interventions, and
  checking system health.

  Scenario: List pipeline runs
    When a user requests the list of pipeline runs
    Then the most recent runs are returned ordered by creation time descending
    And each run includes identification, status, source, cost, and timestamps

  Scenario: Get single pipeline run with per-repo status
    When a user requests a specific pipeline run
    Then the full run details are returned
    And per-repo worker status is included

  Scenario: Retrieve agent conversation
    Given an agent has executed and stored its conversation
    When a user requests the conversation for a specific agent session
    Then the stored conversation messages are returned

  Scenario: Retrieve worker logs
    Given workers have been running for a CR
    When a user requests the worker logs
    Then the worker process logs for all repos in the CR are returned

  Scenario: Release gate status
    Given a CR affects multiple repos
    When a user requests the release gate status
    Then the per-repo PR status is returned
    And the overall readiness for release is indicated

  Scenario: Health check
    When the health endpoint is called
    Then a healthy response is returned

  Scenario: Readiness check
    When the readiness endpoint is called
    Then database and event bus connectivity are verified
    And the response indicates whether the system is ready or not

  # --- Prompt template management ---

  Scenario: List prompt templates
    When a user requests the list of prompt templates
    Then all stored templates are returned with role, description, version, and timestamp

  Scenario: Get a single prompt template
    When a user requests the template for a specific role
    Then the full template content is returned

  Scenario: Update a prompt template
    When a user submits updated content for a role's template
    Then the template is stored with an incremented version
    And an audit log entry is created

  # --- Model settings ---

  Scenario: Get model settings with defaults
    When a user requests model settings and none have been configured
    Then hardcoded defaults are returned for all stages

  Scenario: Update model settings
    When a user submits per-stage backend and model configuration
    Then the settings are persisted
    And an audit log entry is created

  Scenario: List available backends
    When a user requests the available backends list
    Then Claude, OpenAI, Gemini, and OpenCode are returned
    And each backend includes its known model list

  Scenario: Available backends include named OpenCode endpoints
    Given named OpenCode endpoints have been configured
    When a user requests the available backends list
    Then each named endpoint appears as a separate backend entry
    And its display name and model list are included

  # --- OpenCode endpoint management ---

  Scenario: Get OpenCode endpoints when none exist
    When a user requests the OpenCode endpoints list
    Then an empty list is returned

  Scenario: Create OpenCode endpoints
    When a user submits a list of named OpenCode endpoints
    Then all endpoints are persisted with slug, display name, base URL, and models
    And an audit log entry is created

  Scenario: Replace OpenCode endpoints
    Given named OpenCode endpoints exist
    When a user submits a new list of endpoints
    Then the previous endpoints are fully replaced by the new list

  Scenario: Reject duplicate endpoint slugs
    When a user submits endpoints with duplicate slugs
    Then the request is rejected with a validation error
