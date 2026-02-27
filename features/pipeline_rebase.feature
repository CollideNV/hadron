Feature: Rebase and Conflict Resolution
  The rebase stage fetches the latest base branch and rebases the
  feature branch. If conflicts arise, a Conflict Resolver agent
  attempts to resolve them.

  Scenario: Clean rebase with no conflicts
    Given the review stage has passed
    When the rebase node fetches the latest base branch and rebases
    And no conflicts are detected
    Then the full test suite is run post-rebase
    And the pipeline proceeds to delivery

  Scenario: Rebase with conflicts triggers conflict resolver
    Given the rebase encounters merge conflicts
    When the Conflict Resolver agent is invoked
    Then it reads the conflicted files
    And it resolves the conflict markers
    And it writes the resolved files back to the worktree
    And git rebase --continue is executed

  Scenario: Multi-commit rebase with repeated conflicts
    Given a rebase has multiple commits that may each produce conflicts
    When the Conflict Resolver resolves one commit's conflicts
    Then git rebase --continue is executed
    And if another commit has conflicts, the resolver runs again
    And this repeats up to 3 times

  Scenario: Unresolvable conflicts pause the pipeline
    Given the Conflict Resolver cannot resolve the conflicts
    When the maximum conflict resolution attempts are exhausted
    Then the rebase is aborted
    And the pipeline pauses for human intervention

  Scenario: Default routing when rebase state is absent
    Given the pipeline state has no rebase_clean field set
    When the rebase routing decision is made
    Then rebase_clean defaults to true
    And the pipeline proceeds to delivery
