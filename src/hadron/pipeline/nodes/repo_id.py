"""Repo Identification node — MVP: reads affected repos from input."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def repo_id_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Identify affected repositories.

    MVP: Uses the repo info provided at CR intake time. No LLM or landscape intelligence.
    """
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="repo_id"
        ))

    # MVP: repos come from the initial CR submission
    repos = state.get("affected_repos", [])
    if not repos:
        logger.error("No affected repos specified for CR %s", cr_id)
        return {
            "current_stage": "repo_id",
            "status": "failed",
            "error": "No affected repositories specified",
            "stage_history": [{"stage": "repo_id", "status": "failed"}],
        }

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="repo_id",
            data={"repos": [r.get("repo_name", r.get("repo_url", "")) for r in repos]},
        ))

    return {
        "current_stage": "repo_id",
        "stage_history": [{"stage": "repo_id", "status": "completed"}],
    }
