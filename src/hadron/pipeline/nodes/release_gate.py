"""Release Gate node — MVP: auto-approve."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def release_gate_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """MVP: auto-approve the release gate. Log summary for visibility."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="release_gate"
        ))

    # Log summary
    structured_cr = state.get("structured_cr", {})
    logger.info(
        "Release gate (auto-approve) for CR %s: %s",
        cr_id, structured_cr.get("title", ""),
    )

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="release_gate",
            data={"approved": True, "mode": "auto_approve_mvp"},
        ))

    return {
        "release_approved": True,
        "current_stage": "release_gate",
        "stage_history": [{"stage": "release_gate", "status": "completed"}],
    }
