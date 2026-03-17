Feature: Behaviour Translation
  The behaviour translation stage runs a Spec Writer agent that
  converts the structured CR into Gherkin feature files written
  directly to the repo worktree.

  Scenario: Generate behaviour specs from CR
    Given a CR has completed worktree setup
    When the behaviour translation stage executes
    Then the Spec Writer agent is invoked with the CR title, description, and acceptance criteria
    And the agent writes feature files directly to the repo worktree
    And the behaviour specs metadata is stored in the pipeline state

  Scenario: Include feedback on retry from verification
    Given the verification stage has rejected the specs with feedback
    When the behaviour translation stage executes again
    Then the Spec Writer agent receives the previous feedback in its prompt
    And it generates revised feature files incorporating the feedback

  Scenario: Spec Writer operates within repo worktree
    When the Spec Writer agent executes
    Then it can read, write, and list files within the repo worktree
