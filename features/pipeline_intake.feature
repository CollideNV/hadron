Feature: Pipeline Intake
  The intake stage receives a raw change request and uses an AI agent
  to parse it into a structured format with acceptance criteria,
  affected domains, priority, constraints, and risk flags.

  Background:
    Given a running controller instance
    And a connected PostgreSQL database
    And a connected Redis instance

  Scenario: Trigger a new change request
    When a user sends a POST to "/api/pipeline/trigger" with a title, description, source, and repo URL
    Then a CRRun record is created with status "pending"
    And a unique cr_id is returned
    And a worker process is spawned to execute the pipeline

  Scenario: Parse raw CR into structured format
    Given a worker has started for a new CR
    When the intake node executes
    Then the intake parser agent is invoked with the raw CR title and description
    And the agent returns a StructuredCR with title, description, acceptance_criteria, affected_domains, priority, constraints, and risk_flags
    And a STAGE_ENTERED event is emitted for "intake"
    And AGENT_STARTED and AGENT_COMPLETED events are emitted
    And a STAGE_COMPLETED event is emitted for "intake"
    And a COST_UPDATE event is emitted with token counts and USD cost

  Scenario: Intake parser falls back to defaults on unparseable output
    Given the intake parser agent returns malformed JSON
    When the intake node processes the response
    Then it falls back to a default StructuredCR with the raw title and description
    And the pipeline continues without failure

  Scenario: Reject duplicate external IDs
    Given a CRRun already exists with external_id "JIRA-123"
    When a user triggers a new CR with the same external_id "JIRA-123"
    Then the request is rejected
    And no duplicate CRRun is created

  Scenario: Freeze configuration at intake
    Given pipeline defaults are configured
    When a CR is triggered
    Then the current configuration is snapshotted into the CRRun
    And all subsequent stages use the frozen config snapshot
