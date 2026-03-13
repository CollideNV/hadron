Feature: Pipeline Flow
  The worker pipeline executes 10 stages in sequence with conditional
  routing at verification, review, and rebase boundaries. Feedback
  loops allow stages to retry before a circuit breaker pauses
  the pipeline.

  Scenario: Execute full worker pipeline end-to-end
    Given a worker has been spawned for a repo
    When the worker pipeline runs without issues
    Then it executes: intake, repo_id, worktree_setup, behaviour_translation, behaviour_verification, tdd, review, rebase, delivery, release
    And the worker pushes the branch and terminates

  Scenario: Multi-repo CR completes end-to-end
    Given a CR has been triggered with 3 repo URLs
    When all 3 workers complete without issues
    Then the Controller detects all PRs are ready
    And the release gate is presented to the human
    And the CRRun status transitions from "pending" to "running" to "completed" after approval

  Scenario: Verification feedback loop
    Given behaviour verification rejects the specs
    And retries remain
    When the pipeline routes back to behaviour translation
    Then the translation-verification loop repeats up to 3 times

  Scenario: Review feedback loop
    Given the code review rejects the code
    And retries remain
    When the pipeline routes back to TDD
    Then the TDD-review loop repeats up to 3 times

  Scenario: Circuit breaker pauses pipeline
    Given a feedback loop has exhausted its maximum retries
    When the circuit breaker triggers
    Then the pipeline enters the "paused" terminal node
    And the CRRun status is set to "paused"
    And a human must intervene to continue

  Scenario: Pipeline never silently fails
    When an unrecoverable error occurs in any stage
    Then the pipeline pauses or fails with a visible status
    And an appropriate event is emitted
    And the error is recorded in the CRRun

  Scenario: Independent workers for multiple repos
    Given a CR affects multiple repositories
    When the Controller spawns workers
    Then one worker is created per repo
    And each worker runs the full pipeline independently
    And the release gate waits for all workers to push PRs
