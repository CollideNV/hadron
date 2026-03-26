Feature: Live Activity Feed
  The pipelines page includes a real-time activity feed showing all
  active CRs with their current stage, cost, and latest event.

  # NOTE: The global SSE endpoint /api/events/global-stream is currently only
  # available via the dummy server (scripts/dummy_server.py). The real backend
  # (src/hadron/controller/routes/events.py) only provides a per-CR stream at
  # /api/events/stream?cr_id=<id>. The scenarios below describe the intended
  # behaviour as implemented against the dummy server. A real backend
  # global-stream endpoint is needed before these work in production.

  Scenario: Activity feed appears on the pipelines page
    Given the user navigates to the pipelines page
    Then a "Live Activity" section is visible below the CR list

  Scenario: Active CRs appear in the feed (requires global-stream endpoint)
    Given two CRs are currently running
    When the global event stream connects via /api/events/global-stream
    Then both CRs appear in the activity feed
    And each row shows the CR ID, title, current stage, and a status indicator

  Scenario: Feed updates in real-time (requires global-stream endpoint)
    Given a CR is shown in the activity feed
    When the CR enters a new stage
    Then the stage label updates without a page refresh
    And the last event text updates

  Scenario: Cost updates stream in real-time (requires global-stream endpoint)
    Given a CR is shown in the activity feed
    When a cost_update event arrives for that CR
    Then the displayed cost updates

  Scenario: Click activity row to open CR detail
    Given a CR appears in the activity feed
    When the user clicks the activity row
    Then the browser navigates to the CR detail page

  Scenario: Connection status indicator
    Given the activity feed is visible
    Then a connection dot indicates whether the SSE stream is connected
    And a green dot means connected
    And a red dot means disconnected

  Scenario: Empty state when no pipelines are running
    Given no CRs are currently active
    Then the activity feed shows "No active pipelines right now."
