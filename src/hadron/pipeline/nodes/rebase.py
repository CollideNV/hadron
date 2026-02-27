"""Rebase node — rebase feature branch onto latest main, with AI conflict resolution."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import logging
from typing import Any

from hadron.agent.base import AgentTask
from hadron.agent.prompt import PromptComposer
from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import (
    emit_cost_update, make_agent_event_emitter, make_nudge_poller,
    make_tool_call_emitter, store_conversation,
)
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


async def rebase_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch latest main and rebase. If conflicts, use an agent to resolve them."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    agent_backend = configurable.get("agent_backend")
    workspace_dir = configurable.get("workspace_dir", "/tmp/hadron-workspace")
    cr_id = state["cr_id"]

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="rebase"
        ))

    wm = WorktreeManager(workspace_dir)
    redis_client = configurable.get("redis")
    all_clean = True
    conflicts = []
    total_cost = 0.0
    total_input = 0
    total_output = 0

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        default_branch = repo.get("default_branch", "main")

        # Attempt rebase, keeping conflicts in place for agent resolution
        try:
            clean = await wm.rebase_keep_conflicts(worktree_path, default_branch)
        except Exception as e:
            logger.warning("Rebase fetch/start failed for %s (CR %s): %s", repo_name, cr_id, e)
            # If we can't even start the rebase (e.g. network issue), mark clean and skip
            clean = True

        if not clean:
            logger.info("Rebase conflicts detected in %s — invoking conflict resolver agent", repo_name)
            conflicts.append(repo_name)

            # Get conflict details
            conflict_files = await wm.get_conflict_files(worktree_path)

            resolver_model = configurable.get("model", "claude-sonnet-4-20250514")
            explore_model = configurable.get("explore_model", "")
            resolver_tools = ["read_file", "write_file", "list_directory", "run_command"]
            if event_bus:
                await event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.AGENT_STARTED, stage="rebase",
                    data={"role": "conflict_resolver", "repo": repo_name, "conflict_files": conflict_files, "model": resolver_model, "allowed_tools": resolver_tools},
                ))

            # Have the agent resolve conflicts
            composer = PromptComposer()
            system_prompt = composer.compose_system_prompt("conflict_resolver")
            task_payload = f"""## Merge Conflict Resolution

The feature branch `ai/cr-{cr_id}` is being rebased onto `{default_branch}`.

**Conflicting files:** {', '.join(conflict_files)}

Please read each conflicting file, resolve the conflict markers, and write the resolved files.
"""
            user_prompt = composer.compose_user_prompt(task_payload)

            task = AgentTask(
                role="conflict_resolver",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                working_directory=worktree_path,
                model=resolver_model,
                explore_model=explore_model,
                on_tool_call=make_tool_call_emitter(event_bus, cr_id, "rebase", "conflict_resolver", repo_name),
                on_event=make_agent_event_emitter(event_bus, cr_id, "rebase", "conflict_resolver", repo_name),
                nudge_poll=make_nudge_poller(redis_client, cr_id, "conflict_resolver") if redis_client else None,
            )
            result = await agent_backend.execute(task)
            await emit_cost_update(event_bus, cr_id, "rebase", result, total_cost)
            total_cost += result.cost_usd
            total_input += result.input_tokens
            total_output += result.output_tokens

            # Store conversation
            cr_conv_key = ""
            if redis_client and result.conversation:
                cr_conv_key = await store_conversation(redis_client, cr_id, "conflict_resolver", repo_name, result.conversation)

            # Try to continue the rebase
            rebase_continued = await wm.continue_rebase(worktree_path)

            if event_bus:
                await event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.AGENT_COMPLETED, stage="rebase",
                    data={
                        "role": "conflict_resolver", "repo": repo_name,
                        "resolved": rebase_continued,
                        "output": result.output[:2000],
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cost_usd": result.cost_usd,
                        "tool_calls_count": len(result.tool_calls),
                        "round_count": result.round_count,
                        "conversation_key": cr_conv_key,
                    },
                ))

            if rebase_continued:
                logger.info("Conflicts resolved successfully for %s", repo_name)
            else:
                # Rebase --continue may trigger more conflicts on subsequent commits
                # Try up to 3 more times (multi-commit rebases)
                for attempt in range(3):
                    remaining_conflicts = await wm.get_conflict_files(worktree_path)
                    if not remaining_conflicts:
                        break
                    logger.info("Additional conflicts after continue (attempt %d): %s", attempt + 1, remaining_conflicts)

                    task.user_prompt = composer.compose_user_prompt(
                        f"More conflicts after rebase --continue. Files: {', '.join(remaining_conflicts)}. Resolve them."
                    )
                    result = await agent_backend.execute(task)
                    await emit_cost_update(event_bus, cr_id, "rebase", result, total_cost)
                    total_cost += result.cost_usd
                    total_input += result.input_tokens
                    total_output += result.output_tokens

                    rebase_continued = await wm.continue_rebase(worktree_path)
                    if rebase_continued:
                        break

                if not rebase_continued:
                    logger.error("Could not fully resolve rebase conflicts for %s — aborting", repo_name)
                    await wm.abort_rebase(worktree_path)
                    all_clean = False
                else:
                    all_clean = True  # Conflicts resolved
        # else: clean rebase, no conflicts

    # Run full test suite to verify
    test_passed = True
    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        test_command = repo.get("test_command", "pytest")
        passed, output = await run_test_command(worktree_path, test_command, cr_id)
        if not passed:
            test_passed = False
            logger.warning("Post-rebase tests failed for %s: %s", repo_name, output[-500:])

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="rebase",
            data={
                "clean": all_clean,
                "had_conflicts": len(conflicts) > 0,
                "conflicts_resolved": all_clean and len(conflicts) > 0,
                "conflict_repos": conflicts,
                "tests_passed": test_passed,
            },
        ))

    result_state: dict[str, Any] = {
        "rebase_clean": all_clean,
        "rebase_conflicts": conflicts if not all_clean else [],
        "current_stage": "rebase",
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "stage_history": [{"stage": "rebase", "status": "completed"}],
    }

    if not all_clean:
        result_state["status"] = "paused"
        result_state["error"] = f"Unresolved rebase conflicts in: {', '.join(conflicts)}"

    return result_state
