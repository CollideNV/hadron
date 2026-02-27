Feature: Retrospective
  The retrospective stage logs a summary of the pipeline run and
  emits a terminal event. In the MVP it does not write to the
  Knowledge Store.

  Scenario: Log pipeline run summary
    Given the release stage has completed
    When the retrospective node executes
    Then it logs a summary of the pipeline run
    And a PIPELINE_COMPLETED event is emitted with final stats

  Scenario: Record final status in database
    When the pipeline completes
    Then the CRRun status is updated to "completed"
    And the final cost_usd is stored in the CRRun record
