Feature: Controller API
  The FastAPI controller exposes REST endpoints for triggering
  pipelines, listing runs, streaming events, and managing
  interventions. It also provides health and readiness checks.

  Scenario: List pipeline runs
    When a user sends a GET to "/api/pipeline/list"
    Then the last 100 CRRuns are returned ordered by creation time descending
    And each run includes cr_id, title, status, source, external_id, cost_usd, error, created_at, and updated_at

  Scenario: Get single pipeline run
    Given a CRRun exists with cr_id "abc-123"
    When a user sends a GET to "/api/pipeline/abc-123"
    Then the full CRRun details are returned

  Scenario: Retrieve agent conversation
    Given an agent has executed and stored its conversation
    When a user sends a GET to "/api/pipeline/{cr_id}/conversation" with a key
    Then the stored conversation messages are returned

  Scenario: Retrieve worker logs
    Given a worker has been running and logging output
    When a user sends a GET to "/api/pipeline/{cr_id}/logs"
    Then the worker process logs are returned

  Scenario: Health check
    When a user sends a GET to "/healthz"
    Then a 200 response is returned

  Scenario: Readiness check
    When a user sends a GET to "/readyz"
    Then PostgreSQL connectivity is verified
    And Redis connectivity is verified
    And a 200 response is returned if both are healthy
