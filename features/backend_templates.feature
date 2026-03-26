Feature: Backend Templates
  Backend templates define per-provider model configurations. Each template
  (Anthropic, OpenAI, Gemini, or custom OpenCode) has its own per-stage
  model selections. One template is the system default. CR creators can
  pick a template at submission time.

  Scenario: Built-in templates are always available
    When no templates have been configured in the database
    Then the GET endpoint returns three built-in templates: Anthropic, OpenAI, Gemini
    And each template includes available_models from the cost table

  Scenario: View templates on settings page
    When an operator navigates to the settings page
    Then template tabs are displayed for each backend template
    And the default template is indicated with a badge

  Scenario: Edit model selections for a template
    Given the settings page is loaded
    When the operator selects the OpenAI template tab
    Then the stage grid shows only OpenAI models in dropdowns
    When the operator changes a model for the implementation stage
    Then the Save button becomes enabled

  Scenario: Create a custom OpenCode template
    Given the settings page is loaded
    When the operator clicks "+ OpenCode"
    Then a new OpenCode template is added
    And fields for display name, base URL, and available models are shown
    When the operator fills in the template details and clicks Save
    Then the new template is persisted with an audit log entry

  Scenario: Delete a custom OpenCode template
    Given an OpenCode template exists
    When the operator clicks the Delete button on that template
    And the operator saves
    Then the template is removed
    And built-in templates cannot be deleted

  Scenario: Set a template as system default
    Given the settings page is loaded
    When the operator selects a non-default template
    And clicks "Set as Default"
    Then the default badge moves to the selected template
    When the operator saves
    Then the default template slug is persisted with an audit log entry

  Scenario: Select template at CR creation
    Given backend templates are configured
    When the CR creation dialog opens
    Then a template dropdown is displayed
    And the system default template is pre-selected
    When the operator selects a different template and submits
    Then the CR is created with the selected template_slug

  Scenario: Template config is frozen into CR at intake
    Given a CR is triggered with template_slug "openai"
    When the intake route processes the CR
    Then the config snapshot includes template_slug "openai"
    And the template's stage models are frozen into the snapshot
    And subsequent template changes do not affect the running CR

  Scenario: Template persistence and audit trail
    When templates are updated via the PUT endpoint
    Then an audit log entry with action "backend_templates_updated" is created
    When the default template is changed via the PUT endpoint
    Then an audit log entry with action "default_template_updated" is created
