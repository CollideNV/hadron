Feature: Event Streaming
  The pipeline emits real-time events via Redis Streams. Clients
  consume them through an SSE endpoint. Events cover the full
  pipeline lifecycle, agent execution, tests, and cost.

  Scenario: Subscribe to events via SSE
    Given a CR is running
    When a client connects to "GET /api/events/stream?cr_id={cr_id}"
    Then all existing events are replayed first
    And new events are streamed in real-time as they occur
    And there is no gap between replayed and live events
    And the connection closes on terminal events

  Scenario: Gap-free handoff between replay and subscribe
    Given events have been emitted to a CR's stream
    When the SSE endpoint replays existing events
    Then the last stream ID from the replay is captured
    And the live subscription starts from that stream ID
    So that events emitted during the replay are not lost

  Scenario: Emit pipeline lifecycle events
    When a pipeline runs from start to finish
    Then PIPELINE_STARTED is emitted at the beginning
    And STAGE_ENTERED is emitted when each stage begins
    And STAGE_COMPLETED is emitted when each stage finishes
    And PIPELINE_COMPLETED is emitted at the end

  Scenario: Emit agent execution events
    When an agent is invoked within a stage
    Then AGENT_STARTED is emitted with the agent role
    And AGENT_COMPLETED is emitted when the agent finishes

  Scenario: Emit test and review events
    When tests are executed during TDD
    Then TEST_RUN events are emitted with pass/fail status
    When review findings are produced
    Then REVIEW_FINDING events may be emitted

  Scenario: Emit cost tracking events
    When an agent completes execution
    Then a COST_UPDATE event is emitted with input tokens, output tokens, and USD cost

  Scenario: Emit failure and pause events
    When the pipeline encounters a fatal error
    Then a PIPELINE_FAILED event is emitted
    When the pipeline pauses for human intervention
    Then a PIPELINE_PAUSED event is emitted

  Scenario: Store events in Redis Streams
    When an event is emitted
    Then it is appended to the Redis Stream "hadron:cr:{cr_id}:events"
    And a notification is published to "hadron:cr:{cr_id}:events:notify"
