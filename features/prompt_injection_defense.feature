Feature: Prompt Injection Defense
  The pipeline implements a six-layer defense against prompt
  injection attacks, ensuring that malicious CR input cannot
  compromise agent behaviour or system integrity.

  Scenario: Layer 1 - Input screening via role prompts
    When an agent is invoked
    Then its role template includes instructions about handling untrusted input

  Scenario: Layer 2 - Spec firewall
    Given a CR has been translated into Gherkin specs
    When code-writing agents execute
    Then they work from the Gherkin specs, not the raw CR text
    And the raw CR cannot directly influence code generation

  Scenario: Layer 3 - Adversarial security review
    When the Security Reviewer agent executes
    Then it treats the CR as hostile input
    And it specifically looks for prompt injection attempts in the generated code

  Scenario: Layer 4 - Deterministic diff scope analysis
    Given code changes have been produced by the TDD stage
    When the diff scope analyser runs before review
    Then it parses the unified diff using pure Python with no LLM
    And it flags config file changes including Docker, Kubernetes, CI/CD, and Terraform files
    And it flags dependency manifest changes including package.json, requirements.txt, and pyproject.toml
    And the flags are injected as warnings into the Security Reviewer prompt

  Scenario: Layer 5 - Runtime containment
    When an agent executes
    Then it is confined to its worktree directory
    And it cannot access files outside the designated workspace

  Scenario: Layer 6 - Human review option
    When the pipeline pauses at any stage
    Then a human can review the current state
    And they can intervene with instructions before the pipeline continues
