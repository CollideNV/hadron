"""PipelineState — the central data structure flowing through every LangGraph node.

This is a TypedDict (LangGraph requirement). Fields are grouped per adr/orchestration.md §5.2.
Cost fields use Annotated reducers so parallel nodes accumulate correctly.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class StructuredCR(TypedDict, total=False):
    """Parsed change request — output of Intake."""

    title: str
    description: str
    acceptance_criteria: list[str]
    affected_domains: list[str]
    priority: str  # low | medium | high | critical
    constraints: list[str]
    risk_flags: list[str]


class RepoContext(TypedDict, total=False):
    """Per-repo context assembled during pipeline execution."""

    repo_url: str
    repo_name: str
    default_branch: str
    worktree_path: str
    agents_md: str  # contents of AGENTS.md / CLAUDE.md
    test_command: str
    language: str


class BehaviourSpec(TypedDict, total=False):
    """Gherkin specs for a single repo."""

    repo_name: str
    feature_files: dict[str, str]  # filename -> content
    verified: bool
    verification_feedback: str
    verification_iteration: int


class DevResult(TypedDict, total=False):
    """TDD development result for a single repo."""

    repo_name: str
    test_files: dict[str, str]  # filename -> content
    code_files: dict[str, str]  # filename -> content
    test_output: str
    tests_passing: bool
    dev_iteration: int


class ReviewResult(TypedDict, total=False):
    """Code review result for a single repo."""

    repo_name: str
    findings: list[dict[str, Any]]  # {severity, category, file, line, message}
    review_passed: bool
    review_iteration: int


class DeliveryResult(TypedDict, total=False):
    """Delivery verification result for a single repo."""

    repo_name: str
    test_output: str
    tests_passing: bool
    branch_pushed: bool
    pr_url: str


class PipelineState(TypedDict, total=False):
    """Central state object carried through all pipeline nodes.

    LangGraph requires TypedDict. Annotated fields with operator.add
    are reducers — when multiple nodes write to them, values accumulate
    rather than overwrite.
    """

    # --- CR Source ---
    cr_id: str
    source: str  # api | jira | github | ado | slack
    external_id: str
    external_url: str

    # --- Change Request ---
    raw_cr_text: str
    raw_cr_title: str
    structured_cr: StructuredCR

    # --- Repo Context ---
    affected_repos: list[RepoContext]

    # --- Behaviour ---
    behaviour_specs: list[BehaviourSpec]
    behaviour_verified: bool
    verification_loop_count: int

    # --- Development ---
    dev_results: list[DevResult]
    dev_loop_count: int

    # --- Review ---
    review_results: list[ReviewResult]
    review_passed: bool
    review_loop_count: int

    # --- Rebase ---
    rebase_clean: bool
    rebase_conflicts: list[str]

    # --- Delivery ---
    delivery_results: list[DeliveryResult]
    all_delivered: bool

    # --- Release ---
    release_approved: bool
    release_results: list[dict[str, Any]]

    # --- Cost (reducer: accumulates across nodes) ---
    cost_input_tokens: Annotated[int, operator.add]
    cost_output_tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]

    # --- Config snapshot (frozen at intake) ---
    config_snapshot: dict[str, Any]

    # --- Intervention ---
    intervention: str | None  # human override instructions

    # --- Status tracking ---
    current_stage: str
    status: str  # running | paused | completed | failed
    error: str | None
    stage_history: Annotated[list[dict[str, Any]], operator.add]
