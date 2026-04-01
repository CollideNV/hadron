Feature: E2E Testing Stage
  The pipeline conditionally runs E2E tests between implementation and review
  when the repository has E2E test configuration detected or declared.

  Background:
    Given the pipeline is running for a change request
    And the implementation stage has completed

  Scenario: E2E tests run when Playwright is detected
    Given a repository with playwright.config.ts
    When the implementation stage completes
    Then the pipeline routes to the e2e_testing stage
    And existing E2E tests are executed via "npx playwright test"

  Scenario: E2E tests run when Cypress is detected
    Given a repository with cypress.config.ts
    When the implementation stage completes
    Then the pipeline routes to the e2e_testing stage
    And existing E2E tests are executed via "npx cypress run"

  Scenario: E2E tests run when WebdriverIO is detected
    Given a repository with wdio.conf.ts
    When the implementation stage completes
    Then the pipeline routes to the e2e_testing stage
    And existing E2E tests are executed via "npx wdio run"

  Scenario: E2E stage skipped when not configured
    Given a repository without E2E test configuration
    When the implementation stage completes
    Then the pipeline routes directly to review

  Scenario: AGENTS.md override enables E2E tests
    Given a repository without E2E marker files
    And AGENTS.md declares "## E2E test command: npx playwright test"
    When the implementation stage completes
    Then the pipeline routes to the e2e_testing stage

  Scenario: AGENTS.md override disables E2E tests
    Given a repository with playwright.config.ts
    And AGENTS.md declares "## E2E tests: none"
    When the implementation stage completes
    Then the pipeline routes directly to review

  Scenario: E2E agent fixes broken tests
    Given E2E tests that fail after implementation changes
    When the e2e_testing agent runs
    Then the agent updates the broken test assertions
    And E2E tests pass on re-run

  Scenario: E2E agent runs once when tests pass initially
    Given E2E tests that pass on the initial run
    When the e2e_testing stage executes
    Then the agent runs once (attempt 0 always executes)
    And the stage completes with e2e_passed=True

  Scenario: E2E retries exhaust max_e2e_retries
    Given E2E tests that fail after implementation changes
    And max_e2e_retries is configured to 1
    When the e2e_testing agent retries and tests still fail
    Then the stage completes after 1 initial + 2 agent attempts
    And e2e_passed is False

  Scenario: E2E test changes are committed
    Given the e2e_testing agent has modified test files
    When the e2e_testing stage completes
    Then the agent's changes are committed with a descriptive message
    And the commit message indicates whether tests are green or red

  Scenario: E2E stage diff is emitted for review visibility
    Given the e2e_testing agent has modified test files
    When the e2e_testing stage completes
    Then a STAGE_DIFF event is emitted with the test file changes
    And reviewers can see what the E2E agent changed

  Scenario: E2E failures pause the pipeline
    Given E2E tests that fail after max retries
    When the e2e_testing stage completes
    Then the pipeline pauses with e2e_passed=False
    And the pause reason indicates E2E test failure
    And the operator can review the failure output and decide how to proceed

  Scenario: E2E runs after rework
    Given a repository with E2E test configuration
    And the review stage has requested rework
    When the rework stage completes
    Then the pipeline routes to e2e_testing before re-review

  Scenario: Nested E2E config detected in monorepo
    Given a monorepo with frontend/playwright.config.ts
    When worktree setup runs auto-detection
    Then the E2E test command is "cd frontend && npx playwright test"

  Scenario: Symlinks are not followed during detection
    Given a repository with a symlinked subdirectory
    When worktree setup runs auto-detection
    Then the symlinked directory is skipped
