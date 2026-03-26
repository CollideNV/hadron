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

  # --- Backend templates ---

  Scenario: Get templates with built-in defaults
    When a user requests backend templates and none have been configured
    Then three built-in templates are returned: Anthropic, OpenAI, Gemini
    And each includes available_models from the cost table

  Scenario: Update backend templates
    When a user submits updated backend templates
    Then all templates are persisted
    And an audit log entry with action "backend_templates_updated" is created

  Scenario: Reject duplicate template slugs
    When a user submits templates with duplicate slugs
    Then the request is rejected with a validation error

  Scenario: Get default template slug
    When a user requests the default template
    Then the current default slug is returned (falls back to "anthropic")

  Scenario: Set default template slug
    When a user sets a new default template slug
    Then the slug is persisted
    And an audit log entry with action "default_template_updated" is created

  Scenario: Reject unknown default template slug
    When a user tries to set a default slug that doesn't match any template
    Then the request is rejected with a validation error
