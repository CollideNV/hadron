"""Pipeline graph — wires all nodes and conditional edges into a LangGraph CompiledStateGraph."""

from __future__ import annotations

from langgraph.types import RunnableConfig

from langgraph.graph import END, StateGraph

from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.edges import after_rebase, after_review, after_verification
from hadron.pipeline.nodes.behaviour import (
    behaviour_translation_node,
    behaviour_verification_node,
)
from hadron.pipeline.nodes.delivery import delivery_node
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
        → Implementation → Review
            ↕ (review loop)
        → Rebase → Delivery → Release

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

    graph.add_edge("implementation", "review")

    # Conditional: review → rework (retry) | rebase (proceed) | paused (circuit breaker)
    graph.add_conditional_edges(
        "review",
        after_review,
        {"rework": "rework", "rebase": "rebase", "paused": "paused"},
    )

    # Rework always goes back to review
    graph.add_edge("rework", "review")

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
