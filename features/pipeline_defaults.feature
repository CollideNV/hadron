Feature: Pipeline Defaults Configuration
  Operators can view and update global pipeline defaults through the
  settings page. Defaults control circuit breakers, timeouts, and delivery
  strategy. Model selections are managed via backend templates.

  Scenario: View defaults with hardcoded fallback
    When no pipeline defaults have been configured in the database
    Then the GET endpoint returns the hardcoded defaults from config

  Scenario: Update pipeline defaults
    When an operator submits updated pipeline defaults
    Then the new defaults are persisted in the database
    And an audit log entry with action "pipeline_defaults_updated" is created

  Scenario: Updated defaults are returned on subsequent reads
    Given pipeline defaults have been updated
    When the GET endpoint is called
    Then the previously saved values are returned instead of hardcoded defaults

  Scenario: Pipeline defaults section on settings page
    When an operator navigates to the settings page
    Then a Pipeline Defaults section is displayed
    And it shows fields for max loops, max cost, timeouts, and delivery strategy

  Scenario: Editing defaults marks the form dirty
    Given the settings page is loaded
    When the operator changes a pipeline default value
    Then the Save button becomes enabled
    And the Discard button appears

  Scenario: Saving defaults persists all settings atomically
    Given the operator has changed pipeline defaults and backend templates
    When the operator clicks Save
    Then both pipeline defaults and templates are saved together

  Scenario: Defaults are frozen into new CRs at intake
    Given pipeline defaults have been configured
    When a new CR is triggered
    Then the CR's config snapshot includes the current pipeline defaults
    And subsequent changes to defaults do not affect the running CR
