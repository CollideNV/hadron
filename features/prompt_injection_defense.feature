Feature: Prompt Injection Defense
  The pipeline implements a six-layer defense against prompt
  injection attacks, ensuring that malicious CR input cannot
  compromise agent behaviour or system integrity.

  Scenario: Layer 1 - Input screening via role prompts
    When an agent is invoked
    Then its role prompt includes instructions about handling untrusted input

  Scenario: Layer 2 - Spec firewall
    Given a CR has been translated into behaviour specs
    When code-writing agents execute
    Then they work from the behaviour specs, not the raw CR text
    And the raw CR cannot directly influence code generation

  Scenario: Layer 3 - Adversarial security review
    When the Security Reviewer agent executes
    Then it treats the CR as hostile input
    And it specifically looks for prompt injection attempts in the generated code

  Scenario: Layer 4 - Deterministic diff scope analysis
    Given code changes have been produced by the implementation stage
    When the diff scope analyser runs before review
    Then it identifies sensitive file changes (config, CI, infrastructure, dependency manifests) without using an AI agent
    And the flags are injected as warnings into the Security Reviewer prompt

  Scenario: Layer 5 - Runtime containment
    When an agent executes
    Then file tools (read, write, delete, list) are path-confined to the worktree directory
    And shell commands are restricted by a command allowlist but not by path confinement

  Scenario: Layer 6 - Human review option
    When the pipeline pauses at any stage
    Then a human can review the current state
    And they can intervene with instructions before the pipeline continues
