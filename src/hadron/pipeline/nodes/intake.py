"""Intake node — parse raw CR into structured CR using LLM."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import json
import logging
from typing import Any

from hadron.agent.base import AgentTask
from hadron.agent.prompt import PromptComposer
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


async def intake_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Parse raw CR text into a structured change request."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    agent_backend = configurable.get("agent_backend")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="intake"
        ))

    composer = PromptComposer()
    system_prompt = composer.compose_system_prompt("intake_parser")
    user_prompt = f"# Change Request\n\n**Title:** {state.get('raw_cr_title', '')}\n\n**Description:**\n{state.get('raw_cr_text', '')}"

    task = AgentTask(
        role="intake_parser",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        allowed_tools=[],
        model=configurable.get("model", "claude-sonnet-4-20250514"),
    )

    result = await agent_backend.execute(task)

    # Parse JSON from agent output
    try:
        # Try to extract JSON from the response
        text = result.output
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        structured = json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        logger.error("Failed to parse intake output as JSON: %s", result.output[:200])
        structured = {
            "title": state.get("raw_cr_title", ""),
            "description": state.get("raw_cr_text", ""),
            "acceptance_criteria": [],
            "affected_domains": [],
            "priority": "medium",
            "constraints": [],
            "risk_flags": ["intake_parse_failed"],
        }

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="intake",
            data={"structured_cr": structured},
        ))

    return {
        "structured_cr": structured,
        "current_stage": "intake",
        "cost_input_tokens": result.input_tokens,
        "cost_output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "stage_history": [{"stage": "intake", "status": "completed"}],
    }
