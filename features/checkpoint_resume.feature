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
    And unrecognised override keys are ignored

  Scenario: Fresh run with overrides
    Given no checkpoint exists for a CR
    And state overrides have been set
    When a new worker starts
    Then it merges the overrides into the initial state
    And it begins execution from the start
