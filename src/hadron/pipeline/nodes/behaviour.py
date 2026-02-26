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
from hadron.pipeline.nodes import (
    emit_cost_update, make_agent_event_emitter, make_nudge_poller,
    make_tool_call_emitter, store_conversation,
)

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

    redis_client = configurable.get("redis")
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

        spec_model = configurable.get("model", "claude-sonnet-4-20250514")
        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_STARTED,
                stage="behaviour_translation",
                data={"role": "spec_writer", "repo": repo_name, "model": spec_model, "allowed_tools": ["read_file", "write_file", "list_directory", "run_command"]},
            ))

        task = AgentTask(
            role="spec_writer",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            working_directory=worktree_path,
            model=spec_model,
            on_tool_call=make_tool_call_emitter(event_bus, cr_id, "behaviour_translation", "spec_writer", repo_name),
            on_event=make_agent_event_emitter(event_bus, cr_id, "behaviour_translation", "spec_writer", repo_name),
            nudge_poll=make_nudge_poller(redis_client, cr_id, "spec_writer") if redis_client else None,
        )
        result = await agent_backend.execute(task)
        await emit_cost_update(event_bus, cr_id, "behaviour_translation", result)

        # Store conversation
        sw_conv_key = ""
        if redis_client and result.conversation:
            sw_conv_key = await store_conversation(redis_client, cr_id, "spec_writer", repo_name, result.conversation)

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
                data={
                    "role": "spec_writer", "repo": repo_name,
                    "output": result.output[:2000],
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": result.cost_usd,
                    "tool_calls_count": len(result.tool_calls),
                    "round_count": result.round_count,
                    "conversation_key": sw_conv_key,
                },
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

    redis_client = configurable.get("redis")
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

        verifier_model = configurable.get("model", "claude-sonnet-4-20250514")
        task = AgentTask(
            role="spec_verifier",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            working_directory=worktree_path,
            model=verifier_model,
            on_tool_call=make_tool_call_emitter(event_bus, cr_id, "behaviour_verification", "spec_verifier", repo_name),
            on_event=make_agent_event_emitter(event_bus, cr_id, "behaviour_verification", "spec_verifier", repo_name),
            nudge_poll=make_nudge_poller(redis_client, cr_id, "spec_verifier") if redis_client else None,
        )

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_STARTED,
                stage="behaviour_verification",
                data={"role": "spec_verifier", "repo": repo_name, "model": verifier_model, "allowed_tools": task.allowed_tools},
            ))

        result = await agent_backend.execute(task)
        await emit_cost_update(event_bus, cr_id, "behaviour_verification", result, total_cost)
        total_cost += result.cost_usd
        total_input += result.input_tokens
        total_output += result.output_tokens

        # Parse verification result — try multiple extraction strategies
        verification = None
        text = result.output
        for extract in [
            lambda t: t.split("```json")[1].split("```")[0] if "```json" in t else None,
            lambda t: t.split("```")[1].split("```")[0] if "```" in t else None,
            lambda t: t[t.index("{"):t.rindex("}") + 1] if "{" in t else None,
            lambda t: t,
        ]:
            try:
                candidate = extract(text)
                if candidate:
                    verification = json.loads(candidate.strip())
                    break
            except (json.JSONDecodeError, IndexError, ValueError):
                continue

        if verification is None:
            logger.error("Could not parse verifier output for %s: %s", repo_name, text[:500])
            verification = {"verified": False, "feedback": f"Verifier output was not valid JSON: {text[:200]}", "missing_scenarios": [], "issues": ["Output parsing failed"]}

        # Store conversation
        sv_conv_key = ""
        if redis_client and result.conversation:
            sv_conv_key = await store_conversation(redis_client, cr_id, "spec_verifier", repo_name, result.conversation)

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.AGENT_COMPLETED,
                stage="behaviour_verification",
                data={
                    "role": "spec_verifier", "repo": repo_name,
                    "output": result.output[:2000],
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": result.cost_usd,
                    "tool_calls_count": len(result.tool_calls),
                    "round_count": result.round_count,
                    "conversation_key": sv_conv_key,
                },
            ))

        verified = verification.get("verified", True)
        feedback = verification.get("feedback", "")
        missing = verification.get("missing_scenarios", [])
        issues = verification.get("issues", [])

        if not verified:
            all_verified = False
            logger.warning(
                "Verification FAILED for repo %s (iteration %d): feedback=%s, missing=%s, issues=%s",
                repo_name, state.get("verification_loop_count", 0) + 1,
                feedback, missing, issues,
            )
        else:
            logger.info("Verification PASSED for repo %s", repo_name)

        updated_specs.append({
            "repo_name": repo_name,
            "feature_files": {},
            "verified": verified,
            "verification_feedback": feedback,
            "verification_iteration": state.get("verification_loop_count", 0) + 1,
        })

        if event_bus:
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.STAGE_COMPLETED,
                stage=f"behaviour_verification:{repo_name}",
                data={
                    "repo": repo_name,
                    "verified": verified,
                    "feedback": feedback,
                    "missing_scenarios": missing,
                    "issues": issues,
                    "iteration": state.get("verification_loop_count", 0) + 1,
                },
            ))

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="behaviour_verification",
            data={
                "all_verified": all_verified,
                "iteration": state.get("verification_loop_count", 0) + 1,
            },
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
