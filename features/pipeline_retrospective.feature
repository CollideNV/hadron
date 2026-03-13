Feature: Retrospective
  When a worker completes, it persists its result, logs a summary,
  and emits a completion event. Each worker independently updates the
  CR run status to its own final status.

  Scenario: Worker logs pipeline run summary on completion
    Given the release stage has completed
    When the worker persists its result
    Then it logs a summary of the pipeline run
    And a pipeline completed event is emitted with final stats

  Scenario: Record final status in database
    When a worker completes
    Then the per-repo run status is updated to the worker's final status
    And the final cost is stored in the per-repo run record

  Scenario: CR run status reflects last worker to finish
    Given multiple repo workers for a CR are running
    When each worker completes and persists its result
    Then it updates the CR run status to its own final status
    And the last worker to finish determines the CR run status
