Feature: Retrospective
  After every pipeline run (success, pause, or failure), the worker persists
  a structured RunSummary and generates rule-based retrospective insights.
  The retrospective is available via API and displayed in the dashboard.

  # --- Run Summary Persistence ---

  Scenario: Persist run summary on completion
    Given the pipeline has completed successfully
    When the worker persists its result
    Then a RunSummary record is created in the database
    And it includes final status, total cost, and token counts
    And it includes per-stage timing with entered_at and completed_at timestamps
    And it includes loop counts (verification, dev, review)
    And it includes model breakdown data

  Scenario: Persist run summary on pause
    Given the pipeline has paused (e.g. budget exceeded)
    When the worker persists its result
    Then a RunSummary record is created with the pause reason
    And the error is classified into a structured category

  Scenario: Persist run summary on failure
    Given the worker encounters an unhandled exception
    When persist_failure is called
    Then a RunSummary record is created with status "failed"
    And the error is classified (api_error, agent_crash, etc.)

  Scenario: Stage history includes timestamps
    When any pipeline node executes via the pipeline_node decorator
    Then the stage_history entry includes entered_at and completed_at timestamps
    And these timestamps are used to compute per-stage durations in the RunSummary

  # --- Error Classification ---

  Scenario: Classify budget exceeded
    Given a pipeline paused with pause_reason "budget_exceeded"
    Then the error_category is "budget_exceeded"

  Scenario: Classify review circuit breaker
    Given a pipeline paused with pause_reason "circuit_breaker"
    And review_loop_count has reached the configured maximum
    Then the error_category is "review_circuit_breaker"

  Scenario: Classify API errors
    Given a pipeline failed with an error containing "APIError" or "rate limit"
    Then the error_category is "api_error"

  Scenario: Classify agent crashes
    Given a pipeline failed with a generic error (e.g. KeyError)
    Then the error_category is "agent_crash"

  # --- Review Findings Summary ---

  Scenario: Summarise review findings across iterations
    Given a pipeline ran through multiple review/rework cycles
    Then the RunSummary includes a review_findings_summary
    And it lists per-iteration counts of critical, major, minor, and info findings
    And it records whether each iteration passed
    And it records the total finding count and final pass/fail status

  # --- Retrospective Insights ---

  Scenario: Clean first-pass completion
    Given the pipeline completed with all loop counts at 1 and no errors
    Then the retrospective contains a single "info" insight: "Clean first-pass completion"

  Scenario: Spec translation looping
    Given verification_loop_count is greater than 1
    Then the retrospective contains a "warning" insight about spec translation iterations
    And the insight suggests reviewing the translation prompt or spec template

  Scenario: Excessive review cycling
    Given review_loop_count is greater than 2
    Then the retrospective contains a "warning" insight about review/rework cycling

  Scenario: Stalled rework detection
    Given review finding counts are non-decreasing across iterations
    Then the retrospective contains a "warning" insight about stalled rework
    And the insight includes the finding count progression

  Scenario: Cost bottleneck identification
    Given a single stage consumed more than 50% of total pipeline duration
    Then the retrospective contains an "info" insight identifying the bottleneck stage

  Scenario: Throttling impact
    Given throttle_seconds exceeds 60
    Then the retrospective contains a "warning" insight about API rate limiting

  Scenario: Budget exceeded insight
    Given the pipeline paused due to budget_exceeded
    Then the retrospective contains a "critical" insight about the budget limit

  # --- Retrospective API and Events ---

  Scenario: Retrospective event emitted
    When the worker persists its result
    Then a retrospective event is emitted to the event bus
    And the event contains the list of retrospective insights

  Scenario: Retrieve retrospective via API
    Given a pipeline run has completed
    When a client requests GET /api/pipeline/{cr_id}/retrospective
    Then the response includes repo name, final status, duration, cost, and insights

  # --- Frontend ---

  Scenario: View retrospective in the dashboard
    Given a pipeline run has completed with retrospective data
    When the user clicks the "Retrospective" stage in the timeline
    Then a panel displays the retrospective insights
    And each insight shows a severity badge, title, detail, and suggestion
    And insights are sorted by severity (critical first)

  Scenario: Retrospective stage marked as completed
    When a retrospective event is received via SSE
    Then the retrospective stage in the timeline is marked as completed
