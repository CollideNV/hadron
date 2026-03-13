Feature: Pipeline Intake
  The intake stage receives a raw change request and uses an AI agent
  to parse it into a structured format with acceptance criteria,
  affected domains, priority, constraints, and risk flags.

  Background:
    Given a running controller instance

  Scenario: Trigger a new change request with multiple repos
    When a user submits a CR with a title, description, source, and list of repo URLs
    Then a run record is created with status "pending"
    And a unique CR identifier is returned
    And one worker is spawned per repo URL

  Scenario: Trigger a single-repo change request
    When a user submits a CR with a title, description, source, and one repo URL
    Then a run record is created with status "pending"
    And one worker is spawned for that repo

  Scenario: Languages and test commands are auto-detected
    When a user submits a CR
    Then the request does not include language or test command fields
    And these are auto-detected by each worker from the repository

  Scenario: Parse raw CR into structured format
    Given a worker has started for a new CR
    When the intake stage executes
    Then the intake agent is invoked with the raw CR title and description
    And it produces a structured CR with acceptance criteria, domains, priority, constraints, and risk flags

  Scenario: Emit lifecycle events during intake
    Given a worker has started for a new CR
    When the intake stage executes
    Then stage entered and stage completed events are emitted
    And agent started and agent completed events are emitted
    And a cost update event is emitted

  Scenario: Fall back to defaults on unparseable output
    Given the intake agent returns output that cannot be parsed
    When the intake stage processes the response
    Then it falls back to a default structured CR with the raw title and description
    And the pipeline pauses for human review

  Scenario: Reject duplicate external IDs
    Given a run already exists with a specific external ID
    When a user triggers a new CR with the same external ID
    Then the request is rejected

  Scenario: Freeze configuration at intake
    When a CR is triggered
    Then the current configuration is snapshotted into the run record
    And all subsequent stages use the frozen config snapshot
