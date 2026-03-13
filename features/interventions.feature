Feature: Human Interventions
  Humans can intervene in a running or paused pipeline by setting
  instructions, sending nudges to specific agents, or resuming
  paused or failed pipelines with state overrides.

  Scenario: Set intervention on a running worker
    When a user submits intervention instructions for a CR
    Then the instructions are stored for the CR
    And the worker picks them up before the next stage execution

  Scenario: Consume intervention atomically
    Given an intervention has been set for a CR
    When the worker checks for an intervention
    Then the intervention is returned and cleared in one operation
    And subsequent checks return nothing until a new intervention is set

  Scenario: Send a nudge to a specific agent
    When a user sends a nudge with a role and message for a CR
    Then the nudge is stored for the specified agent role
    And the agent picks up the nudge between tool-use rounds

  Scenario: Resume a paused or failed worker
    Given a CR has workers in "paused" or "failed" status
    When a user submits a resume request with state overrides
    Then the worker status is updated to "running"
    And new workers are spawned for all paused or failed repos
    And a pipeline resumed event is emitted

  Scenario: Resume with review override
    Given a CR is paused after a failed review
    When a user resumes with an override marking the review as passed
    Then the worker resumes from the review stage

  Scenario: Resume with rebase override
    Given a CR is paused after unresolved rebase conflicts
    When a user resumes with an override marking the rebase as clean
    Then the worker resumes from the rebase stage

  Scenario: Reject resume of a non-paused and non-failed pipeline
    Given a CR is in "running" status
    When a user submits a resume request
    Then the request is rejected because only paused or failed runs can be resumed
