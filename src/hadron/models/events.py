"""Event models emitted by pipeline stages to the event bus."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    PIPELINE_PAUSED = "pipeline_paused"
    STAGE_ENTERED = "stage_entered"
    STAGE_COMPLETED = "stage_completed"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_OUTPUT = "agent_output"
    AGENT_NUDGE = "agent_nudge"
    TEST_RUN = "test_run"
    REVIEW_FINDING = "review_finding"
    INTERVENTION_SET = "intervention_set"
    COST_UPDATE = "cost_update"
    ERROR = "error"


class PipelineEvent(BaseModel):
    """Base event emitted to the event bus."""

    cr_id: str
    event_type: EventType
    stage: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
