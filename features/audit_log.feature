Feature: Audit Log Viewer
  Operators can view a timestamped audit trail of all significant
  actions performed on the system.

  Scenario: View audit log
    When an operator navigates to the audit log page
    Then recent audit entries are displayed in a table
    And each entry shows timestamp, action, CR ID, and details

  Scenario: Filter by action type
    Given audit entries of various action types exist
    When the operator selects an action type filter
    Then only entries matching that action type are displayed

  # Backend audit actions: backend_templates_updated, default_template_updated,
  # pipeline_defaults_updated, prompt_template_updated.

  Scenario: Clear action filter
    Given an action filter is active
    When the operator clicks the All filter
    Then all entries are displayed regardless of action type

  Scenario: Paginate through entries
    Given there are more audit entries than the page size
    When the operator clicks Next
    Then the next page of entries is displayed

  Scenario: Empty state
    When no audit entries exist
    Then an informational message is displayed

  Scenario: CR link in audit entries
    Given an audit entry has an associated CR ID
    Then the CR ID is displayed as a link to the CR detail page

  Scenario: Audit log is accessible from the navigation
    When an operator looks at the main navigation
    Then an Audit link is visible between Prompts and Settings
