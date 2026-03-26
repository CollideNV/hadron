Feature: CI Integration
  When a worker uses the push_and_wait delivery strategy, it pushes a
  branch and terminates. An external CI system sends results back via
  webhook, and the controller spawns a new worker to resume.

  Scenario: CI webhook triggers resume after push_and_wait
    Given a worker has pushed a branch and terminated (push_and_wait strategy)
    When the external CI system sends results via POST /pipeline/{cr_id}/ci-result
    Then the controller stores the CI result
    And spawns a new worker to resume the pipeline

  Scenario: CI pass resumes to delivery
    Given a CI result webhook reports tests passed for a repo
    When the worker resumes
    Then it proceeds through review, rebase, and delivery as normal

  Scenario: CI failure resumes with failure context
    Given a CI result webhook reports tests failed for a repo
    When the worker resumes
    Then the CI failure log is passed as a state override
    And the implementation agent receives the CI failure context
