Feature: CR List Search and Filters
  Operators can search, filter by status, and sort the pipeline
  runs list to quickly find relevant CRs.

  Scenario: Search by title
    Given pipeline runs exist with various titles
    When the operator types a search term
    Then only runs whose title contains the term are displayed

  Scenario: Search by CR ID
    When the operator searches for a CR ID
    Then the matching run is displayed

  Scenario: Search is debounced
    When the operator types quickly in the search field
    Then the API is not called on every keystroke
    And the search executes after typing pauses

  Scenario: Filter by single status
    Given pipeline runs exist in various statuses
    When the operator clicks a status filter chip
    Then only runs in that status are displayed

  Scenario: Filter by multiple statuses
    When the operator selects multiple status filter chips
    Then runs in any of the selected statuses are displayed

  Scenario: Clear status filters
    Given status filters are active
    When the operator clicks the Clear button
    Then all status filters are removed and all runs are shown

  Scenario: Sort by newest first
    When the sort is set to Newest (default)
    Then runs are ordered by creation time descending

  Scenario: Sort by oldest first
    When the operator changes sort to Oldest
    Then runs are ordered by creation time ascending

  Scenario: Sort by highest cost
    When the operator changes sort to Highest cost
    Then runs are ordered by cost descending

  Scenario: Combined search and filter
    When the operator searches and filters simultaneously
    Then both constraints are applied to the results

  Scenario: Empty state with active filters
    When search or filters produce no matching runs
    Then a message suggests adjusting the search or filters
