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
