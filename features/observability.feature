Feature: Observability Stack
  Hadron provides three layers of production observability: structured logging
  (structlog), Prometheus metrics, and OpenTelemetry distributed tracing.
  Metrics and tracing are optional extras; logging is always available.

  # ── Structured Logging ────────────────────────────────────────────────────

  Scenario: Controller starts with structured JSON logging
    Given the environment variable HADRON_LOG_FORMAT is set to "json"
    When the controller starts
    Then all log output should be newline-delimited JSON
    And each log entry should contain "event", "level", and "timestamp" fields

  Scenario: Controller starts with human-readable text logging
    Given the environment variable HADRON_LOG_FORMAT is set to "text"
    When the controller starts
    Then log output should be coloured human-readable text

  Scenario: Worker logs include CR and repo context
    Given a worker is processing CR "CR-42" for repo "my-repo"
    When the worker emits a log entry
    Then the log entry should contain "cr_id": "CR-42"
    And the log entry should contain "repo_name": "my-repo"

  Scenario: Pipeline stage binds context to all logs
    Given a pipeline node is executing the "review" stage for CR "CR-42"
    When the node emits log entries
    Then all entries should contain "cr_id": "CR-42" and "stage": "review"

  Scenario: Agent run binds role context
    Given the "security_reviewer" agent is running within the "review" stage
    When the agent emits log entries
    Then all entries should contain "agent_role": "security_reviewer"

  Scenario: HTTP requests include a unique request ID
    When a client sends a GET request to any controller endpoint
    Then the response should include an "X-Request-ID" header
    And the request ID should appear in the corresponding log entries

  Scenario: Incoming request ID is preserved
    Given a client sends a request with header X-Request-ID "abc-123"
    When the controller processes the request
    Then the response X-Request-ID header should be "abc-123"

  Scenario: Redis log handler always emits JSON
    Given the worker's console log format is "text"
    When the worker writes logs to Redis for the dashboard
    Then the Redis log entries should be JSON regardless of the console format

  # ── Prometheus Metrics ────────────────────────────────────────────────────

  Scenario: Metrics endpoint available when prometheus-client is installed
    Given the [observability] extra is installed
    When a client sends a GET request to "/metrics"
    Then the response status code should be 200
    And the Content-Type should be "text/plain; version=0.0.4; charset=utf-8"
    And the body should contain Prometheus text exposition format metrics

  Scenario: Metrics endpoint returns 501 without prometheus-client
    Given the [observability] extra is NOT installed
    When a client sends a GET request to "/metrics"
    Then the response status code should be 501

  Scenario: HTTP request metrics are recorded
    Given the [observability] extra is installed
    When a client sends multiple requests to the controller
    Then the "/metrics" output should include "hadron_http_requests_total"
    And the "/metrics" output should include "hadron_http_request_duration_seconds"

  Scenario: Pipeline metrics are recorded via worker relay
    Given a worker completes a pipeline run for CR "CR-42"
    When the worker publishes its metrics to the "hadron:metrics" Redis channel
    Then the controller's background listener should record:
      | metric                              | labels               |
      | hadron_pipeline_runs_total          | status="completed"   |
      | hadron_pipeline_cost_usd_total      | cr_id="CR-42"        |

  Scenario: Agent metrics are recorded
    Given a worker completes an agent invocation
    When the metrics payload includes role, model, and token counts
    Then the controller should record:
      | metric                     | labels                    |
      | hadron_agent_runs_total    | role, model               |
      | hadron_agent_tokens_total  | direction="input", model  |
      | hadron_agent_tokens_total  | direction="output", model |

  Scenario: Metrics gracefully no-op without the extra
    Given the [observability] extra is NOT installed
    When pipeline code records metrics (e.g. incrementing a counter)
    Then no error should be raised
    And the metric call should silently do nothing

  # ── OpenTelemetry Tracing ─────────────────────────────────────────────────

  Scenario: Tracing is disabled by default
    Given HADRON_OTEL_ENABLED is not set or is "false"
    When the controller or worker starts
    Then no OpenTelemetry tracer provider should be configured
    And all span() calls should return no-op contexts with zero overhead

  Scenario: Tracing can be enabled via environment variable
    Given HADRON_OTEL_ENABLED is set to "true"
    And HADRON_OTLP_ENDPOINT is set to "http://jaeger:4317"
    When the controller starts
    Then an OTLP gRPC span exporter should be configured
    And spans should be exported to "http://jaeger:4317"

  Scenario: Pipeline stages create spans
    Given tracing is enabled
    When the pipeline executes the "implementation" stage
    Then a span named "pipeline.implementation" should be created
    And the span should have attributes "cr_id" and "stage"

  Scenario: Agent invocations create nested spans
    Given tracing is enabled
    When the "implementation_agent" runs within the "implementation" stage
    Then a span named "agent.implementation_agent" should be nested under "pipeline.implementation"
    And it should have attributes "role", "stage", and "model"

  Scenario: Backend phases create nested spans
    Given tracing is enabled
    When an agent executes the explore, plan, and act phases
    Then spans "backend.explore", "backend.plan", and "backend.act" should be created
    And each should be nested under the parent agent span

  Scenario: LLM API calls and tool executions create leaf spans
    Given tracing is enabled
    When the tool loop makes an LLM API call and executes a tool
    Then a span named "llm.act" should be created for the API call
    And a span named "tool.{tool_name}" should be created for each tool execution

  Scenario: Trace context propagates from controller to worker
    Given tracing is enabled on the controller
    When the controller spawns a worker subprocess
    Then the worker's environment should contain a TRACEPARENT variable
    And the worker should restore the trace context on startup
    And worker spans should appear as children of the controller's span

  Scenario: Trace context propagates to K8s worker jobs
    Given tracing is enabled on the controller
    When the controller creates a K8s Job for a worker
    Then the Job's container env should include TRACEPARENT
    And the worker pod's spans should join the same trace

  Scenario: Tracing gracefully no-ops without the extra
    Given the [observability] extra is NOT installed
    When pipeline code uses span() context managers
    Then no error should be raised
    And the span should be a no-op that yields None
