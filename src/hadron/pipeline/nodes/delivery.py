"""Delivery node — dispatches to the configured delivery strategy.

Strategies:
- ``self_contained``: run full test suite, push only on success.
- ``push_and_wait``: push branch unconditionally, pause for external CI callback.
- ``push_and_forget``: push branch unconditionally, proceed immediately.
"""

from __future__ import annotations

import logging
from typing import Any

from hadron.config.limits import TEST_OUTPUT_BRIEF_CHARS
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, pipeline_node
from hadron.pipeline.nodes.diff_capture import emit_stage_diff
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


def _get_delivery_strategy(state: PipelineState) -> str:
    return (
        state.get("config_snapshot", {})
        .get("pipeline", {})
        .get("delivery_strategy", "self_contained")
    )


async def _push_branch(
    ctx: NodeContext, ri: RepoInfo, cr_id: str,
) -> bool:
    """Commit outstanding changes and push.  Returns True on success."""
    try:
        await ctx.worktree_manager.commit_and_push(
            ri.worktree_path, f"chore: delivery push for {cr_id}",
        )
        return True
    except RuntimeError as e:
        logger.warning("Push failed for %s: %s", ri.repo_name, e)
        return False


async def _self_contained(
    state: PipelineState, ctx: NodeContext, cr_id: str, ri: RepoInfo,
) -> dict[str, Any]:
    """Run tests, push only if they pass."""
    tests_passing, test_output = await run_test_command(
        ri.worktree_path, ri.test_command, cr_id,
    )

    branch_pushed = False
    if tests_passing:
        branch_pushed = await _push_branch(ctx, ri, cr_id)

    if branch_pushed:
        await emit_stage_diff(
            ctx.event_bus, cr_id, "delivery", ri.repo_name,
            ctx.worktree_manager, ri.worktree_path, ri.default_branch,
        )

    all_delivered = tests_passing and branch_pushed

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="delivery",
        data={"strategy": "self_contained", "all_delivered": all_delivered},
    ))

    return {
        "delivery_results": [{
            "repo_name": ri.repo_name,
            "test_output": test_output[-TEST_OUTPUT_BRIEF_CHARS:],
            "tests_passing": tests_passing,
            "branch_pushed": branch_pushed,
            "pr_url": "",
        }],
        "all_delivered": all_delivered,
        "current_stage": "delivery",
        "stage_history": [{"stage": "delivery", "status": "completed"}],
    }


async def _push_and_wait(
    state: PipelineState, ctx: NodeContext, cr_id: str, ri: RepoInfo,
) -> dict[str, Any]:
    """Push branch unconditionally and pause for external CI callback.

    The worker terminates here.  When the CI webhook fires
    ``POST /pipeline/{cr_id}/ci-result``, the Controller resumes
    the worker with the CI outcome injected into state.
    """
    branch_pushed = await _push_branch(ctx, ri, cr_id)

    if branch_pushed:
        await emit_stage_diff(
            ctx.event_bus, cr_id, "delivery", ri.repo_name,
            ctx.worktree_manager, ri.worktree_path, ri.default_branch,
        )

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.PIPELINE_PAUSED, stage="delivery",
        data={
            "strategy": "push_and_wait",
            "reason": "waiting_for_ci",
            "branch_pushed": branch_pushed,
        },
    ))

    return {
        "delivery_results": [{
            "repo_name": ri.repo_name,
            "test_output": "",
            "tests_passing": False,
            "branch_pushed": branch_pushed,
            "pr_url": "",
        }],
        "all_delivered": False,
        "status": "paused",
        "pause_reason": "waiting_for_ci",
        "current_stage": "delivery",
        "stage_history": [{"stage": "delivery", "status": "paused"}],
    }


async def _push_and_forget(
    state: PipelineState, ctx: NodeContext, cr_id: str, ri: RepoInfo,
) -> dict[str, Any]:
    """Push branch unconditionally and proceed immediately to release."""
    branch_pushed = await _push_branch(ctx, ri, cr_id)

    if branch_pushed:
        await emit_stage_diff(
            ctx.event_bus, cr_id, "delivery", ri.repo_name,
            ctx.worktree_manager, ri.worktree_path, ri.default_branch,
        )

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="delivery",
        data={"strategy": "push_and_forget", "all_delivered": branch_pushed},
    ))

    return {
        "delivery_results": [{
            "repo_name": ri.repo_name,
            "test_output": "",
            "tests_passing": True,  # skipped — no local verification
            "branch_pushed": branch_pushed,
            "pr_url": "",
        }],
        "all_delivered": branch_pushed,
        "current_stage": "delivery",
        "stage_history": [{"stage": "delivery", "status": "completed"}],
    }


_STRATEGIES = {
    "self_contained": _self_contained,
    "push_and_wait": _push_and_wait,
    "push_and_forget": _push_and_forget,
}


@pipeline_node("delivery")
async def delivery_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Dispatch to the configured delivery strategy."""
    strategy = _get_delivery_strategy(state)
    ri = RepoInfo.from_state(state)

    handler = _STRATEGIES.get(strategy)
    if handler is None:
        logger.error("Unknown delivery strategy %r, falling back to self_contained", strategy)
        handler = _self_contained

    return await handler(state, ctx, cr_id, ri)
