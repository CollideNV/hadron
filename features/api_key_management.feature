Feature: API Key Management
  Operators can configure API keys for backend providers via the
  settings dashboard. Keys are encrypted at rest in the database
  and never exposed in full via the API.

  Background:
    Given HADRON_ENCRYPTION_KEY is set in the environment

  Scenario: API key shown within backend template tab
    When an operator navigates to the settings page
    And selects a backend template tab (e.g. Anthropic)
    Then the API key status for that backend is shown within the tab
    And it displays the masked value, source badge, and set/clear controls

  Scenario: View API key status when no keys are configured
    Given no API keys are stored in the database
    And no API key environment variables are set
    When an operator views a backend template tab
    Then the API key row shows "Not configured" with source "Not set"

  Scenario: View API key status with environment variable fallback
    Given no API keys are stored in the database
    And HADRON_ANTHROPIC_API_KEY is set in the environment
    When the operator views the Anthropic template tab
    Then the API key row shows as configured with source "Environment"
    And the masked value shows the last 4 characters only

  Scenario: Set an API key via the dashboard
    When the operator enters a new Anthropic API key in the template tab and saves
    Then the key is encrypted with Fernet and stored in the database
    And the status updates to source "Database" with a masked value
    And an audit log entry "api_key_updated" is created with key_name only

  Scenario: Database keys take priority over environment variables
    Given HADRON_ANTHROPIC_API_KEY is set in the environment
    And a different Anthropic key is stored in the database
    When the controller spawns a worker
    Then the worker receives the database-stored key via HADRON_ANTHROPIC_API_KEY

  Scenario: Clear a database-stored key
    Given an Anthropic key is stored in the database
    When the operator clicks Clear on the Anthropic key
    Then the key is removed from the database
    And the status falls back to environment variable if set
    And an audit log entry "api_key_cleared" is created with key_name only

  Scenario: API never returns full key values
    Given an Anthropic key "sk-ant-secret-long-key" is stored in the database
    When the GET /settings/api-keys endpoint is called
    Then the response contains only the masked value (last 4 characters)
    And no plaintext key appears in the response body

  Scenario: Config snapshots do not include API keys
    Given API keys are configured in the database
    When a CR is triggered and the config snapshot is frozen
    Then the config_snapshot_json does not contain any API key values
    And the config_snapshot_json does not contain the "api_keys" setting key

  Scenario: Audit log entries do not include key values
    When an API key is set or cleared via the dashboard
    Then the audit log details contain only the key_name field
    And no actual key value appears in the audit log details

  Scenario: Encryption key is required for storing keys
    Given HADRON_ENCRYPTION_KEY is not set in the environment
    When the operator attempts to set an API key via the PUT endpoint
    Then the request returns a 503 error
    And the error message indicates encryption is not configured

  Scenario: Workers receive resolved keys at spawn time
    Given API keys are stored in the database
    When the controller spawns a worker subprocess
    Then the worker's environment includes the decrypted API keys as HADRON_* env vars
    And the worker does not need database access to read API keys
