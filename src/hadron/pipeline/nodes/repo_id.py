"""Repo Identification node — MVP: validates repo from worker input."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext

logger = logging.getLogger(__name__)


async def repo_id_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Validate the repo assigned to this worker.

    MVP: Each worker receives its repo from the Controller at spawn time.
    No LLM or landscape intelligence needed.
    """
    ctx = NodeContext.from_config(config)
    cr_id = state["cr_id"]

    await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="repo_id"
        ))

    repo = state.get("repo", {})
    if not repo or not repo.get("repo_url"):
        logger.error("No repo specified for worker (CR %s)", cr_id)
        return {
            "current_stage": "repo_id",
            "status": "failed",
            "error": "No repository specified for this worker",
            "stage_history": [{"stage": "repo_id", "status": "failed"}],
        }

    repo_name = repo.get("repo_name") or repo.get("repo_url", "").rstrip("/").split("/")[-1]
    if not repo_name:
        logger.error("Could not determine repo name for worker (CR %s)", cr_id)
        return {
            "current_stage": "repo_id",
            "status": "failed",
            "error": "Could not determine repository name",
            "stage_history": [{"stage": "repo_id", "status": "failed"}],
        }

    await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="repo_id",
            data={"repo": repo_name},
        ))

    return {
        "current_stage": "repo_id",
        "stage_history": [{"stage": "repo_id", "status": "completed"}],
    }
