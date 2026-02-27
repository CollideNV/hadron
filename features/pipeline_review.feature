Feature: Code Review
  The review stage runs three specialised reviewer agents in parallel:
  Security Reviewer, Quality Reviewer, and Spec Compliance Reviewer.
  A deterministic diff scope pre-pass flags sensitive file changes.

  Scenario: Run three reviewers in parallel
    Given the TDD stage has completed
    When the review node executes
    Then the Security Reviewer, Quality Reviewer, and Spec Compliance Reviewer run in parallel
    And each reviewer produces findings with severity, category, file, line, message, and reviewer name

  Scenario: Security Reviewer treats CR as untrusted
    When the Security Reviewer executes
    Then it receives the CR marked as untrusted input
    And it receives diff scope flags from the deterministic pre-pass
    And it receives the behaviour specs for context
    And it has read_file and list_directory tools available

  Scenario: Quality Reviewer evaluates code quality
    When the Quality Reviewer executes
    Then it receives the CR, acceptance criteria, and diff
    And it evaluates architecture, performance, and code quality

  Scenario: Spec Compliance Reviewer checks against specs
    When the Spec Compliance Reviewer executes
    Then it receives the CR, acceptance criteria, and this repo's full specs
    And it receives other repos' spec summaries for cross-repo awareness
    And it evaluates whether the code matches the behaviour specs

  Scenario: Review passes with no critical or major findings
    Given all three reviewers return findings with only minor or info severity
    When the review results are merged
    Then the review is marked as passed
    And the pipeline proceeds to the rebase stage

  Scenario: Review fails with critical or major findings and retries remaining
    Given at least one reviewer returns a critical or major finding
    And the review loop count is below the maximum of 3
    When the review routing decision is made
    Then the pipeline routes back to the TDD stage with the findings
    And the review loop count is incremented

  Scenario: Review fails with no retries remaining
    Given the review has failed
    And the review loop count has reached the maximum of 3
    When the review routing decision is made
    Then the pipeline pauses with a circuit breaker

  Scenario: Deterministic diff scope analysis
    Given the TDD stage has produced code changes
    When the review node performs a diff scope pre-pass
    Then it identifies config files without using an LLM
    And it identifies dependency manifest changes without using an LLM
    And it produces ScopeFlag warnings injected into the Security Reviewer prompt
