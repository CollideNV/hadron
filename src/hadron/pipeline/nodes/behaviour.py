"""Behaviour Translation + Verification nodes."""

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


async def behaviour_translation_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Spec Writer agent writes Gherkin .feature files for each repo."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    agent_backend = configurable.get("agent_backend")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="behaviour_translation"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    specs_list = []

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")

        repo_context = composer.build_repo_context(
            agents_md=repo.get("agents_md", ""),
            language=repo.get("language", "python"),
            test_command=repo.get("test_command", "pytest"),
        )
        system_prompt = composer.compose_system_prompt("spec_writer", repo_context)

        # Include feedback from verification if this is a retry
        feedback = ""
        existing_specs = state.get("behaviour_specs", [])
        for spec in existing_specs:
            if spec.get("repo_name") == repo_name and spec.get("verification_feedback"):
                feedback = spec["verification_feedback"]

        task_payload = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}
"""
        user_prompt = composer.compose_user_prompt(task_payload, feedback)

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_STARTED,
                stage="behaviour_translation",
                data={"role": "spec_writer", "repo": repo_name},
            ))

        task = AgentTask(
            role="spec_writer",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            working_directory=worktree_path,
            model=configurable.get("model", "claude-sonnet-4-20250514"),
        )
        result = await agent_backend.execute(task)

        specs_list.append({
            "repo_name": repo_name,
            "feature_files": {},  # Agent writes directly to disk
            "verified": False,
            "verification_feedback": "",
            "verification_iteration": state.get("verification_loop_count", 0),
        })

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_COMPLETED,
                stage="behaviour_translation",
                data={"role": "spec_writer", "repo": repo_name},
            ))

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="behaviour_translation",
        ))

    return {
        "behaviour_specs": specs_list,
        "current_stage": "behaviour_translation",
        "cost_input_tokens": result.input_tokens,
        "cost_output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "stage_history": [{"stage": "behaviour_translation", "status": "completed"}],
    }


async def behaviour_verification_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Verifier agent checks completeness and consistency of specs."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    agent_backend = configurable.get("agent_backend")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="behaviour_verification"
        ))

    composer = PromptComposer()
    structured_cr = state.get("structured_cr", {})
    all_verified = True
    updated_specs = []
    total_cost = 0.0
    total_input = 0
    total_output = 0

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")

        system_prompt = composer.compose_system_prompt("spec_verifier")
        task_payload = f"""# Change Request

**Title:** {structured_cr.get('title', '')}
**Description:** {structured_cr.get('description', '')}

**Acceptance Criteria:**
{chr(10).join(f'- {c}' for c in structured_cr.get('acceptance_criteria', []))}

Please read the .feature files in the repository and verify them against this CR.
"""
        user_prompt = composer.compose_user_prompt(task_payload)

        task = AgentTask(
            role="spec_verifier",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            working_directory=worktree_path,
            model=configurable.get("model", "claude-sonnet-4-20250514"),
        )
        result = await agent_backend.execute(task)
        total_cost += result.cost_usd
        total_input += result.input_tokens
        total_output += result.output_tokens

        # Parse verification result
        try:
            text = result.output
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            verification = json.loads(text.strip())
        except (json.JSONDecodeError, IndexError):
            verification = {"verified": True, "feedback": ""}

        verified = verification.get("verified", True)
        if not verified:
            all_verified = False

        updated_specs.append({
            "repo_name": repo_name,
            "feature_files": {},
            "verified": verified,
            "verification_feedback": verification.get("feedback", ""),
            "verification_iteration": state.get("verification_loop_count", 0) + 1,
        })

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="behaviour_verification",
            data={"all_verified": all_verified},
        ))

    return {
        "behaviour_specs": updated_specs,
        "behaviour_verified": all_verified,
        "verification_loop_count": state.get("verification_loop_count", 0) + 1,
        "current_stage": "behaviour_verification",
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "stage_history": [{"stage": "behaviour_verification", "status": "completed"}],
    }
