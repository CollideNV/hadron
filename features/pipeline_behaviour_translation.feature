Feature: Behaviour Translation
  The behaviour translation stage runs a Spec Writer agent that
  converts the structured CR into Gherkin .feature files written
  directly to the repo worktree.

  Scenario: Generate behaviour specs from CR
    Given a CR has completed worktree setup
    When the behaviour translation node executes
    Then the Spec Writer agent is invoked with the CR title, description, and acceptance criteria
    And the agent writes .feature files directly to the repo worktree
    And the behaviour specs metadata is stored in the pipeline state

  Scenario: Run spec writer per repo in parallel
    Given a CR affects multiple repos
    When the behaviour translation node executes
    Then a Spec Writer agent runs for each repo
    And all agents can execute in parallel

  Scenario: Include feedback on retry from verification
    Given the verification stage has rejected the specs with feedback
    When the behaviour translation node executes again
    Then the Spec Writer agent receives the previous feedback in its prompt
    And it generates revised .feature files incorporating the feedback

  Scenario: Spec Writer has file system tools
    When the Spec Writer agent executes
    Then it has access to read_file, write_file, list_directory, and run_command tools
    And it operates within the repo worktree directory
