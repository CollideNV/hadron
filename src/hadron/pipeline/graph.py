"""Pipeline graph — wires all nodes and conditional edges into a LangGraph CompiledStateGraph."""

from __future__ import annotations

from langgraph.types import RunnableConfig

from langgraph.graph import END, StateGraph

from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.edges import (
    after_implementation,
    after_rebase,
    after_review,
    after_rework,
    after_verification,
)
from hadron.pipeline.nodes.behaviour import (
    behaviour_translation_node,
    behaviour_verification_node,
)
from hadron.pipeline.nodes.delivery import delivery_node
from hadron.pipeline.nodes.e2e_testing import e2e_testing_node
from hadron.pipeline.nodes.intake import intake_node
from hadron.pipeline.nodes.rebase import rebase_node
from hadron.pipeline.nodes.release import release_node
from hadron.pipeline.nodes.repo_id import repo_id_node
from hadron.pipeline.nodes.review import review_node
from hadron.pipeline.nodes.implementation import implementation_node
from hadron.pipeline.nodes.rework import rework_node
from hadron.pipeline.nodes.worktree_setup import worktree_setup_node


def _paused_node(state: PipelineState, config: RunnableConfig) -> dict:
    """Terminal node for circuit breaker pauses."""
    return {"status": "paused", "stage_history": [{"stage": "paused", "status": "paused"}]}


def build_pipeline_graph() -> StateGraph:
    """Build the worker pipeline graph (one repo per worker).

    Graph structure follows adr/orchestration.md §5.3:
        Intake → Repo ID → Worktree Setup → Behaviour Translation → Behaviour Verification
            ↕ (verification loop)
        → Implementation → [E2E Testing] → Review
            ↕ (review loop via rework → [E2E Testing])
        → Rebase → Delivery → Release

    E2E Testing is conditional — only runs when the repo has E2E test
    commands configured (auto-detected or via AGENTS.md).

    Release gate (human approval) and retrospective are handled by the Controller
    after all repo workers for a CR have completed.
    """
    graph = StateGraph(PipelineState)

    # Add all nodes
    graph.add_node("intake", intake_node)
    graph.add_node("repo_id", repo_id_node)
    graph.add_node("worktree_setup", worktree_setup_node)
    graph.add_node("translation", behaviour_translation_node)
    graph.add_node("verification", behaviour_verification_node)
    graph.add_node("implementation", implementation_node)
    graph.add_node("rework", rework_node)
    graph.add_node("e2e_testing", e2e_testing_node)
    graph.add_node("review", review_node)
    graph.add_node("rebase", rebase_node)
    graph.add_node("delivery", delivery_node)
    graph.add_node("release", release_node)
    graph.add_node("paused", _paused_node)

    # Linear edges
    graph.set_entry_point("intake")
    graph.add_edge("intake", "repo_id")
    graph.add_edge("repo_id", "worktree_setup")
    graph.add_edge("worktree_setup", "translation")
    graph.add_edge("translation", "verification")

    # Conditional: verification → translation (retry) | implementation (proceed) | paused (circuit breaker)
    graph.add_conditional_edges(
        "verification",
        after_verification,
        {"translation": "translation", "implementation": "implementation", "paused": "paused"},
    )

    # Conditional: implementation → e2e_testing (if configured) | review (no E2E) | paused
    graph.add_conditional_edges(
        "implementation",
        after_implementation,
        {"e2e_testing": "e2e_testing", "review": "review", "paused": "paused"},
    )

    # E2E testing always flows into review
    graph.add_edge("e2e_testing", "review")

    # Conditional: review → rework (retry) | rebase (proceed) | paused (circuit breaker)
    graph.add_conditional_edges(
        "review",
        after_review,
        {"rework": "rework", "rebase": "rebase", "paused": "paused"},
    )

    # Conditional: rework → e2e_testing (if configured) | review (no E2E) | paused
    graph.add_conditional_edges(
        "rework",
        after_rework,
        {"e2e_testing": "e2e_testing", "review": "review", "paused": "paused"},
    )

    # Conditional: rebase → delivery (clean) | paused (conflicts)
    graph.add_conditional_edges(
        "rebase",
        after_rebase,
        {"delivery": "delivery", "paused": "paused"},
    )

    graph.add_edge("delivery", "release")
    graph.add_edge("release", END)
    graph.add_edge("paused", END)

    return graph
