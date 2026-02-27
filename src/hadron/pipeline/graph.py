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
from hadron.pipeline.nodes.release_gate import release_gate_node
from hadron.pipeline.nodes.repo_id import repo_id_node
from hadron.pipeline.nodes.retrospective import retrospective_node
from hadron.pipeline.nodes.review import review_node
from hadron.pipeline.nodes.tdd import tdd_node
from hadron.pipeline.nodes.worktree_setup import worktree_setup_node


def _paused_node(state: PipelineState, config: RunnableConfig) -> dict:
    """Terminal node for circuit breaker pauses."""
    return {"status": "paused", "stage_history": [{"stage": "paused", "status": "paused"}]}


def build_pipeline_graph() -> StateGraph:
    """Build the complete pipeline graph.

    Graph structure follows adr/orchestration.md §5.3:
        Intake → Repo ID → Worktree Setup → Behaviour Translation → Behaviour Verification
            ↕ (verification loop)
        → TDD → Review
            ↕ (review loop)
        → Rebase → Delivery → Release Gate → Release → Retrospective
    """
    graph = StateGraph(PipelineState)

    # Add all nodes
    graph.add_node("intake", intake_node)
    graph.add_node("repo_id", repo_id_node)
    graph.add_node("worktree_setup", worktree_setup_node)
    graph.add_node("translation", behaviour_translation_node)
    graph.add_node("verification", behaviour_verification_node)
    graph.add_node("tdd", tdd_node)
    graph.add_node("review", review_node)
    graph.add_node("rebase", rebase_node)
    graph.add_node("delivery", delivery_node)
    graph.add_node("release_gate", release_gate_node)
    graph.add_node("release", release_node)
    graph.add_node("retrospective", retrospective_node)
    graph.add_node("paused", _paused_node)

    # Linear edges
    graph.set_entry_point("intake")
    graph.add_edge("intake", "repo_id")
    graph.add_edge("repo_id", "worktree_setup")
    graph.add_edge("worktree_setup", "translation")
    graph.add_edge("translation", "verification")

    # Conditional: verification → translation (retry) | tdd (proceed) | paused (circuit breaker)
    graph.add_conditional_edges(
        "verification",
        after_verification,
        {"translation": "translation", "tdd": "tdd", "paused": "paused"},
    )

    graph.add_edge("tdd", "review")

    # Conditional: review → tdd (retry) | rebase (proceed) | paused (circuit breaker)
    graph.add_conditional_edges(
        "review",
        after_review,
        {"tdd": "tdd", "rebase": "rebase", "paused": "paused"},
    )

    # Conditional: rebase → delivery (clean) | paused (conflicts)
    graph.add_conditional_edges(
        "rebase",
        after_rebase,
        {"delivery": "delivery", "paused": "paused"},
    )

    graph.add_edge("delivery", "release_gate")
    graph.add_edge("release_gate", "release")
    graph.add_edge("release", "retrospective")
    graph.add_edge("retrospective", END)
    graph.add_edge("paused", END)

    return graph
