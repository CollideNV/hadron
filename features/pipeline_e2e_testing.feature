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

  Scenario: E2E agent writes new tests
    Given a CR that adds new user-facing functionality
    When the e2e_testing agent runs
    Then new E2E tests are written for the new functionality
    And E2E tests pass

  Scenario: E2E failures proceed to review with context
    Given E2E tests that fail after max retries
    When the e2e_testing stage completes
    Then the pipeline proceeds to review with e2e_passed=False
    And reviewers can see the E2E failure output

  Scenario: E2E runs after rework
    Given a repository with E2E test configuration
    And the review stage has requested rework
    When the rework stage completes
    Then the pipeline routes to e2e_testing before re-review

  Scenario: Nested E2E config detected in monorepo
    Given a monorepo with frontend/playwright.config.ts
    When worktree setup runs auto-detection
    Then the E2E test command is "cd frontend && npx playwright test"
