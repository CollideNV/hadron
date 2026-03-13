Feature: Retrospective
  The retrospective is a Controller-level concern, not a worker pipeline
  node. When a worker completes, it persists its result (via
  worker/main.py:persist_result), logs a summary, and emits a
  PIPELINE_COMPLETED event. The Controller tracks worker completion
  and updates the CRRun status.

  Scenario: Worker logs pipeline run summary on completion
    Given the release node has completed
    When the worker persists its result
    Then it logs a summary of the pipeline run
    And a PIPELINE_COMPLETED event is emitted with final stats

  Scenario: Record final status in database
    When the worker completes successfully
    Then the RepoRun status is updated to "completed"
    And the final cost_usd is stored in the RepoRun record

  Scenario: Controller updates CRRun when all workers finish
    Given all repo workers for a CR have completed
    When the Controller detects all repos are done
    Then the CRRun status is updated to "completed"
