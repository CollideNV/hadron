"""Rebase node — rebase feature branch onto latest main, with AI conflict resolution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hadron.agent.base import CostAccumulator
from hadron.config.defaults import BRANCH_PREFIX
from hadron.config.limits import REBASE_OUTPUT_TAIL_CHARS
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, pipeline_node, run_agent
from hadron.pipeline.testing import run_test_command

logger = logging.getLogger(__name__)


@pipeline_node("rebase")
async def rebase_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Fetch latest main and rebase. If conflicts, use an agent to resolve them."""
    wm = ctx.worktree_manager
    rebase_clean = True
    had_conflicts = False
    costs = CostAccumulator()

    ri = RepoInfo.from_state(state)

    # Attempt rebase, keeping conflicts in place for agent resolution
    try:
        clean = await wm.rebase_keep_conflicts(ri.worktree_path, ri.default_branch)
    except RuntimeError as e:
        logger.warning("Rebase fetch/start failed for %s (CR %s): %s", ri.repo_name, cr_id, e)
        clean = True

    if not clean:
        conflict_files = await wm.get_conflict_files(ri.worktree_path)

        if not conflict_files:
            # Rebase failed but no conflict markers — likely an empty rebase,
            # "nothing to do", or already-applied patches.  Abort the
            # in-progress rebase (if any) and treat as clean.
            logger.warning("Rebase returned non-clean but no conflict files found for %s — aborting and treating as clean", ri.repo_name)
            await wm.abort_rebase(ri.worktree_path)
            clean = True  # no real conflicts

    if not clean and conflict_files:
        logger.info("Rebase conflicts detected in %s — invoking conflict resolver agent", ri.repo_name)
        had_conflicts = True

        # Pre-read conflicting files (capped per file to avoid bloating the prompt)
        MAX_CONFLICT_FILE_CHARS = 10_000
        base = Path(ri.worktree_path)
        file_contents = ""
        for cf in conflict_files:
            cf_path = base / cf
            if cf_path.is_file():
                content = cf_path.read_text(errors="replace")
                if len(content) > MAX_CONFLICT_FILE_CHARS:
                    content = content[:MAX_CONFLICT_FILE_CHARS] + f"\n\n... (truncated, use read_file for full content)"
                file_contents += f"### {cf}\n\n```\n{content}\n```\n\n"

        composer = ctx.prompt_composer
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
            prior_cost=costs.total_cost,
            explore_model="",  # No explore/plan — conflict files are injected directly
            plan_model="",
        )
        costs.add(agent_run.result)

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
                    prior_cost=costs.total_cost,
                    explore_model="",
                    plan_model="",
                )
                costs.add(retry_run.result)

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
        logger.warning("Post-rebase tests failed for %s: %s", ri.repo_name, output[-REBASE_OUTPUT_TAIL_CHARS:])

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
        **costs.to_state_dict(),
        "stage_history": [{"stage": "rebase", "status": "completed"}],
    }

    if not rebase_clean:
        result_state["status"] = "paused"
        result_state["error"] = f"Unresolved rebase conflicts in: {ri.repo_name}"

    return result_state
