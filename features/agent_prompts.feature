Feature: Agent Prompt Composition
  Agent prompts are composed in four layers: role template, repo
  context, task payload, and loop feedback. Templates can be
  customised and are frozen into the config snapshot at intake.

  Scenario: Compose agent prompts in four layers
    When an agent prompt is composed
    Then Layer 1 is the role system prompt from the template
    And Layer 2 is the repo context including agent instructions, language, and directory tree
    And Layer 3 is the task payload with CR details, specs, and code
    And Layer 4 is loop feedback from previous stages

  Scenario: Custom prompt templates override defaults
    Given a custom prompt template has been saved for a role
    When that role's agent prompt is composed
    Then the custom template is used instead of the default
    And templates are frozen into the config snapshot at intake

  Scenario: System prompt truncated to context limit
    Given a repo has a very large AGENTS.md file
    When the system prompt is composed
    Then it is truncated to the maximum context size
