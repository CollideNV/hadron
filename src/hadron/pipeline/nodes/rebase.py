"""Rebase node — rebase feature branch onto latest main, with AI conflict resolution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hadron.agent.prompt import PromptComposer
from hadron.config.defaults import BRANCH_PREFIX
from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, pipeline_node, run_agent
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


@pipeline_node("rebase")
async def rebase_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Fetch latest main and rebase. If conflicts, use an agent to resolve them."""
    wm = WorktreeManager(ctx.workspace_dir)
    rebase_clean = True
    had_conflicts = False
    total_cost = 0.0
    total_input = 0
    total_output = 0

    ri = RepoInfo.from_state(state)

    # Attempt rebase, keeping conflicts in place for agent resolution
    try:
        clean = await wm.rebase_keep_conflicts(ri.worktree_path, ri.default_branch)
    except RuntimeError as e:
        logger.warning("Rebase fetch/start failed for %s (CR %s): %s", ri.repo_name, cr_id, e)
        clean = True

    if not clean:
        logger.info("Rebase conflicts detected in %s — invoking conflict resolver agent", ri.repo_name)
        had_conflicts = True

        conflict_files = await wm.get_conflict_files(ri.worktree_path)

        # Pre-read conflicting files so the agent doesn't need to explore
        base = Path(ri.worktree_path)
        file_contents = ""
        for cf in conflict_files:
            cf_path = base / cf
            if cf_path.is_file():
                content = cf_path.read_text(errors="replace")
                file_contents += f"### {cf}\n\n```\n{content}\n```\n\n"

        composer = PromptComposer()
        system_prompt = composer.compose_system_prompt("conflict_resolver")
        task_payload = f"""## Merge Conflict Resolution

The feature branch `{BRANCH_PREFIX}{cr_id}` is being rebased onto `{ri.default_branch}`.

**Conflicting files:** {', '.join(conflict_files)}

## Current File Contents (with conflict markers)

{file_contents}

Resolve the conflict markers in each file and write the resolved versions.
"""
        user_prompt = composer.compose_user_prompt(task_payload)

        agent_run = await run_agent(
            ctx,
            role="conflict_resolver",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cr_id=cr_id,
            stage="rebase",
            repo_name=ri.repo_name,
            working_directory=ri.worktree_path,
            prior_cost=total_cost,
            explore_model="",  # No explore/plan — conflict files are injected directly
            plan_model="",
        )
        total_cost += agent_run.result.cost_usd
        total_input += agent_run.result.input_tokens
        total_output += agent_run.result.output_tokens

        # Try to continue the rebase
        rebase_continued = await wm.continue_rebase(ri.worktree_path)

        if rebase_continued:
            logger.info("Conflicts resolved successfully for %s", ri.repo_name)
        else:
            # Rebase --continue may trigger more conflicts on subsequent commits.
            # Try up to 3 more times (multi-commit rebases).
            for attempt in range(3):
                remaining_conflicts = await wm.get_conflict_files(ri.worktree_path)
                if not remaining_conflicts:
                    break
                logger.info("Additional conflicts after continue (attempt %d): %s", attempt + 1, remaining_conflicts)

                retry_payload = f"More conflicts after rebase --continue. Files: {', '.join(remaining_conflicts)}. Resolve them."
                retry_run = await run_agent(
                    ctx,
                    role="conflict_resolver",
                    system_prompt=system_prompt,
                    user_prompt=composer.compose_user_prompt(retry_payload),
                    cr_id=cr_id,
                    stage="rebase",
                    repo_name=ri.repo_name,
                    working_directory=ri.worktree_path,
                    prior_cost=total_cost,
                    explore_model="",
                    plan_model="",
                )
                total_cost += retry_run.result.cost_usd
                total_input += retry_run.result.input_tokens
                total_output += retry_run.result.output_tokens

                rebase_continued = await wm.continue_rebase(ri.worktree_path)
                if rebase_continued:
                    break

            if not rebase_continued:
                logger.error("Could not fully resolve rebase conflicts for %s — aborting", ri.repo_name)
                await wm.abort_rebase(ri.worktree_path)
                rebase_clean = False

    # Run full test suite to verify
    passed, output = await run_test_command(ri.worktree_path, ri.test_command, cr_id)
    test_passed = passed
    if not passed:
        logger.warning("Post-rebase tests failed for %s: %s", ri.repo_name, output[-500:])

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="rebase",
        data={
            "clean": rebase_clean,
            "had_conflicts": had_conflicts,
            "conflicts_resolved": rebase_clean and had_conflicts,
            "repo": ri.repo_name,
            "tests_passed": test_passed,
        },
    ))

    result_state: dict[str, Any] = {
        "rebase_clean": rebase_clean,
        "rebase_conflicts": [ri.repo_name] if not rebase_clean else [],
        "current_stage": "rebase",
        "cost_input_tokens": total_input,
        "cost_output_tokens": total_output,
        "cost_usd": total_cost,
        "stage_history": [{"stage": "rebase", "status": "completed"}],
    }

    if not rebase_clean:
        result_state["status"] = "paused"
        result_state["error"] = f"Unresolved rebase conflicts in: {ri.repo_name}"

    return result_state
