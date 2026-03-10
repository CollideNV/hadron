Feature: Controller API
  The FastAPI controller exposes REST endpoints for triggering
  pipelines, listing runs, streaming events, and managing
  interventions. It also provides health and readiness checks.

  Scenario: List pipeline runs
    When a user sends a GET to "/api/pipeline/list"
    Then the last 100 CRRuns are returned ordered by creation time descending
    And each run includes cr_id, title, status, source, external_id, cost_usd, error, created_at, and updated_at

  Scenario: Get single pipeline run with per-repo status
    Given a CRRun exists with cr_id "abc-123"
    When a user sends a GET to "/api/pipeline/abc-123"
    Then the full CRRun details are returned
    And per-repo worker status is included

  Scenario: Retrieve agent conversation
    Given an agent has executed and stored its conversation
    When a user sends a GET to "/api/pipeline/{cr_id}/conversation" with a key
    Then the stored conversation messages are returned

  Scenario: Retrieve worker logs per repo
    Given a worker has been running for a specific repo
    When a user sends a GET to "/api/pipeline/{cr_id}/logs?repo={repo_name}"
    Then the worker process logs for that repo are returned

  Scenario: Release gate status
    Given a CR affects multiple repos
    When a user sends a GET to "/api/pipeline/{cr_id}/release-status"
    Then the per-repo PR status is returned
    And the overall readiness for release is indicated

  Scenario: Health check
    When a user sends a GET to "/healthz"
    Then a 200 response is returned

  Scenario: Readiness check
    When a user sends a GET to "/readyz"
    Then PostgreSQL connectivity is verified
    And Redis connectivity is verified
    And a 200 response is returned if both are healthy
