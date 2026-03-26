Feature: CR Creation Dialog
  The CR creation form is presented in a modal dialog launched from
  the CR list page, replacing the former dedicated /new route.

  Scenario: Open the creation dialog from the CR list page
    Given the user is on the CR list page
    When the user activates the create CR trigger
    Then the CR creation dialog opens
    And the CR creation form is displayed inside the dialog

  Scenario: Close the dialog with the Cancel button
    Given the CR creation dialog is open
    When the user clicks the Cancel button
    Then the dialog closes
    And the user remains on the CR list page

  Scenario: Close the dialog with the Escape key
    Given the CR creation dialog is open
    When the user presses the Escape key
    Then the dialog closes
    And the user remains on the CR list page

  Scenario: Successful form submission closes the dialog
    Given the CR creation dialog is open
    And the user has filled in a valid CR title, description, and repo URLs
    When the user submits the form
    Then a new CR is created
    And the dialog closes
    And the user is returned to the CR list page

  Scenario: Submit button is disabled when required fields are empty
    Given the CR creation dialog is open
    When the title or description field is empty
    Then the submit button is disabled
    And the dialog remains open

  Scenario: /new route is removed
    When the user navigates directly to the /new route
    Then they are redirected to the CR list page

  Scenario: Dialog styling is consistent with the application design system
    Given the CR creation dialog is open
    Then the dialog appearance matches the application design system

  Scenario: Template selector visible with default pre-selected
    Given backend templates are configured with a system default
    When the CR creation dialog opens
    Then a backend template dropdown is visible
    And the system default template is pre-selected in the dropdown
