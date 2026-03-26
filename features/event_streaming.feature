Feature: Event Streaming
  The pipeline emits real-time events covering the full lifecycle:
  stage transitions, agent execution, test results, cost updates,
  and failure/pause notifications. Clients consume events via SSE.

  Scenario: Subscribe to events via SSE
    Given a CR is running
    When a client connects to the event stream
    Then all existing events are replayed first
    And new events are streamed in real-time as they occur
    And there is no gap between replayed and live events
    And the connection closes on pipeline_completed or pipeline_failed events

  Scenario: No events lost during reconnection
    Given events have been emitted for a CR
    When the SSE endpoint replays existing events
    Then the live subscription starts from where the replay left off
    So that events emitted during the replay are not lost

  Scenario: Pipeline lifecycle events
    When a pipeline runs from start to finish
    Then a started event is emitted at the beginning
    And a stage entered event is emitted when each stage begins
    And a stage completed event is emitted when each stage finishes
    And a completed event is emitted at the end

  Scenario: Agent execution events
    When an agent is invoked within a stage
    Then an agent started event is emitted with the agent role
    And an agent completed event is emitted when the agent finishes

  Scenario: Test and review events
    When tests are executed during implementation
    Then test run events are emitted with pass/fail status
    When review findings are produced
    Then review finding events may be emitted

  Scenario: Cost tracking events
    When an agent completes execution
    Then a cost update event is emitted with incremental cost delta and cumulative total cost

  Scenario: Stage diff events
    When a stage produces code or spec changes
    Then a stage diff event is emitted with the unified diff
    And the diff includes file change statistics
    And large diffs are truncated with a flag

  Scenario: Failure and pause events
    When the pipeline encounters a fatal error
    Then a pipeline failed event is emitted
    When the pipeline pauses for human intervention
    Then a pipeline paused event is emitted
