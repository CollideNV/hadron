Feature: Checkpoint and Resume
  Workers checkpoint pipeline state after each stage. If a worker
  terminates, a new worker can resume from the last checkpoint.
  State overrides can redirect execution to a specific stage.

  Scenario: Checkpoint state after each stage
    When a pipeline stage completes
    Then the pipeline state is checkpointed to persistent storage
    And any worker can resume from this checkpoint

  Scenario: Resume from checkpoint on worker restart
    Given a worker has terminated after checkpointing
    When a new worker is spawned for the same CR and repo
    Then it loads the latest checkpoint
    And it resumes execution from the last completed stage

  Scenario: Resume with state overrides
    Given a checkpoint exists for a paused CR
    And state overrides have been set via the resume endpoint
    When a new worker starts
    Then it applies the overrides to the checkpointed state
    And it resumes from the stage corresponding to the override

  Scenario: Override routing selects the appropriate stage
    Given multiple state overrides are present
    When the worker determines the resume point
    Then it selects the stage that is latest in pipeline order among recognised overrides
    And if no override keys match a recognised stage the worker resumes from the paused node

  Scenario: Fresh run with overrides
    Given no checkpoint exists for a CR
    And state overrides have been set
    When a new worker starts
    Then it merges the overrides into the initial state
    And it begins execution from the start

  Scenario: CI webhook triggers resume after push_and_wait
    Given a worker has pushed a branch and terminated (push_and_wait strategy)
    When the external CI system sends results via POST /pipeline/{cr_id}/ci-result
    Then the controller stores the CI result
    And spawns a new worker to resume the pipeline

  Scenario: CI pass resumes to delivery
    Given a CI result webhook reports tests passed for a repo
    When the worker resumes
    Then it proceeds through review, rebase, and delivery as normal

  Scenario: CI failure resumes with failure context
    Given a CI result webhook reports tests failed for a repo
    When the worker resumes
    Then the CI failure log is passed as a state override
    And the implementation agent receives the CI failure context
