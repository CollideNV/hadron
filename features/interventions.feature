Feature: Human Interventions
  Humans can intervene in a running or paused pipeline by setting
  instructions, sending nudges to specific agents, or resuming
  paused pipelines with state overrides.

  Scenario: Set intervention on a running CR
    When a user sends a POST to "/api/pipeline/{cr_id}/intervene" with instructions
    Then the instructions are stored in Redis at "hadron:cr:{cr_id}:intervention"
    And the worker picks up the intervention before the next node execution

  Scenario: Consume intervention atomically
    Given an intervention has been set for a CR
    When the worker polls for the intervention
    Then the intervention is returned and deleted atomically
    And subsequent polls return nothing until a new intervention is set

  Scenario: Send a nudge to a specific agent
    When a user sends a POST to "/api/pipeline/{cr_id}/nudge" with a role and message
    Then the nudge is stored in Redis at "hadron:cr:{cr_id}:nudge:{role}"
    And the agent picks up the nudge between tool-use rounds

  Scenario: Resume a paused pipeline
    Given a CR is in "paused" status
    When a user sends a POST to "/api/pipeline/{cr_id}/resume" with state overrides
    Then the CRRun status is updated to "running"
    And the overrides are stored in Redis with a 1-hour TTL
    And a new worker is spawned
    And a PIPELINE_RESUMED event is emitted

  Scenario: Resume with review override
    Given a CR is paused after a failed review
    When a user resumes with state override "review_passed: true"
    Then the worker resumes from the "review" node
    And the review is marked as passed in the state

  Scenario: Resume with rebase override
    Given a CR is paused after unresolved rebase conflicts
    When a user resumes with state override "rebase_clean: true"
    Then the worker resumes from the "rebase" node

  Scenario: Reject resume of a non-paused pipeline
    Given a CR is in "running" status
    When a user sends a POST to "/api/pipeline/{cr_id}/resume"
    Then the request is rejected
