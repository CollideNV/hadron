"""Retrospective node — MVP stub: log pipeline run summary."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def retrospective_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """MVP stub: log pipeline run summary. No Knowledge Store writes."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="retrospective"
        ))

    structured_cr = state.get("structured_cr", {})
    logger.info(
        "Retrospective for CR %s (%s): dev_loops=%d, review_loops=%d, cost=$%.4f",
        cr_id,
        structured_cr.get("title", ""),
        state.get("dev_loop_count", 0),
        state.get("review_loop_count", 0),
        state.get("cost_usd", 0),
    )

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_COMPLETED, stage="retrospective",
            data={
                "title": structured_cr.get("title", ""),
                "dev_loops": state.get("dev_loop_count", 0),
                "review_loops": state.get("review_loop_count", 0),
                "cost_usd": state.get("cost_usd", 0),
            },
        ))

    return {
        "current_stage": "retrospective",
        "status": "completed",
        "stage_history": [{"stage": "retrospective", "status": "completed"}],
    }
