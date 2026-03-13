Feature: Code Review
  The review stage runs three specialised reviewer agents in parallel:
  Security Reviewer, Quality Reviewer, and Spec Compliance Reviewer.
  A deterministic diff scope pre-pass flags sensitive file changes.

  Scenario: Run three reviewers in parallel
    Given the TDD stage has completed
    When the review stage executes
    Then the Security, Quality, and Spec Compliance reviewers run in parallel
    And each reviewer produces findings with severity, category, file, line, and message

  Scenario: Security Reviewer treats CR as untrusted
    When the Security Reviewer executes
    Then it receives the CR marked as untrusted input
    And it receives diff scope flags from the deterministic pre-pass
    And it receives the behaviour specs for context

  Scenario: Quality Reviewer evaluates code quality
    When the Quality Reviewer executes
    Then it receives the CR title, acceptance criteria, and diff
    And it evaluates architecture, performance, and code quality

  Scenario: Spec Compliance Reviewer checks against specs
    When the Spec Compliance Reviewer executes
    Then it receives the CR title, acceptance criteria, and this repo's full specs
    And it receives other repos' spec summaries for cross-repo awareness
    And it evaluates whether the code matches the behaviour specs

  Scenario: Review passes with no blocking findings
    Given all three reviewers return findings with only minor or info severity
    When the review results are merged
    Then the review is marked as passed
    And the pipeline proceeds to the rebase stage

  Scenario: Review fails with blocking findings and retries remaining
    Given at least one reviewer returns a critical or major finding
    And the review loop count is below the maximum (default 3)
    When the review routing decision is made
    Then the pipeline routes back to the TDD stage with the findings
    And the review loop count is incremented

  Scenario: Review fails with no retries remaining
    Given the review has failed
    And the review loop count has reached the maximum (default 3)
    When the review routing decision is made
    Then the pipeline pauses with a circuit breaker

  Scenario: Custom review loop limit
    Given a custom review loop limit is configured
    When the review routing decision is made
    Then the custom limit is used instead of the default 3

  Scenario: Deterministic diff scope analysis
    Given the TDD stage has produced code changes
    When the review stage performs a diff scope pre-pass
    Then it identifies config file changes without using an AI agent
    And it identifies dependency manifest changes without using an AI agent
    And the flags are injected as warnings into the Security Reviewer prompt
