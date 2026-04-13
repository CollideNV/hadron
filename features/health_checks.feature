Feature: Kubernetes Health Check Endpoints
  To ensure reliable operation within a Kubernetes environment, the controller
  provides distinct endpoints for liveness, readiness, and general health status.

  Scenario: Liveness probe indicates the server is running
    When a client sends a GET request to "/livez"
    Then the response status code should be 200 OK
    And the response body should be a simple confirmation

  Scenario: Readiness probe succeeds when all dependencies are healthy
    Given all dependencies including PostgreSQL and Redis are reachable
    When a client sends a GET request to "/readyz"
    Then the response status code should be 200 OK

  Scenario: Readiness probe fails when PostgreSQL is unavailable
    Given the PostgreSQL dependency is unreachable
    When a client sends a GET request to "/readyz"
    Then the response status code should be 503 Service Unavailable

  Scenario: Readiness probe fails when Redis is unavailable
    Given the Redis dependency is unreachable
    When a client sends a GET request to "/readyz"
    Then the response status code should be 503 Service Unavailable

  Scenario: Health endpoint provides application status
    When a client sends a GET request to "/healthz"
    Then the response status code should be 200 OK
    And the response body should be a JSON object
    And the JSON response should contain the application "version"
    And the JSON response should contain the server "uptime" in seconds
