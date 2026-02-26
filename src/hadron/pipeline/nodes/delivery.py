"""Delivery node — self_contained strategy: run tests and push branch."""

from __future__ import annotations

from langgraph.types import RunnableConfig

import asyncio
import logging
from typing import Any

from hadron.git.worktree import WorktreeManager
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState

import os

logger = logging.getLogger(__name__)


async def delivery_node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
    """Self-contained delivery: run full test suite, then push final branch."""
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    workspace_dir = configurable.get("workspace_dir", "/tmp/hadron-workspace")
    cr_id = state["cr_id"]
    
    logger.info("Entering delivery node for CR %s", cr_id)

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_ENTERED, stage="delivery"
        ))

    wm = WorktreeManager(workspace_dir)
    delivery_results = []
    
    # Prevent git from prompting for credentials
    git_env = os.environ.copy()
    git_env["GIT_TERMINAL_PROMPT"] = "0"

    for repo in state.get("affected_repos", []):
        repo_name = repo.get("repo_name", "")
        worktree_path = repo.get("worktree_path", "")
        test_command = repo.get("test_command", "pytest")
        
        logger.info("Running pre-delivery tests for %s in %s", repo_name, worktree_path)

        # Run full test suite
        try:
            # Ensure we are in the correct directory
            if not test_command.startswith("cd "):
                test_command = f"cd {worktree_path} && {test_command}"
                
            proc = await asyncio.create_subprocess_shell(
                test_command, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.STDOUT,
                env=git_env,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            test_output = stdout.decode(errors="replace")
            tests_passing = proc.returncode == 0
            logger.info("Tests finished for %s (passed=%s)", repo_name, tests_passing)
        except asyncio.TimeoutError:
            logger.error("Tests timed out for %s", repo_name)
            test_output = "Tests timed out after 120s"
            tests_passing = False
            if 'proc' in locals():
                try:
                    proc.kill()
                except:
                    pass
        except Exception as e:
            logger.error("Test execution failed for %s: %s", repo_name, e)
            test_output = str(e)
            tests_passing = False

        # Push branch
        branch_pushed = False
        if tests_passing:
            try:
                logger.info("Pushing changes for %s", repo_name)
                # Add timeout to push to prevent hanging on credentials
                await asyncio.wait_for(
                    wm.commit_and_push(worktree_path, f"chore: final push for {cr_id}"),
                    timeout=60
                )
                branch_pushed = True
                logger.info("Push successful for %s", repo_name)
            except asyncio.TimeoutError:
                logger.error("Push timed out for %s (likely credential issue)", repo_name)
            except Exception as e:
                logger.warning("Push failed for %s: %s", repo_name, e)

        delivery_results.append({
            "repo_name": repo_name,
            "test_output": test_output[-2000:],
            "tests_passing": tests_passing,
            "branch_pushed": branch_pushed,
            "pr_url": "",
        })

    all_delivered = all(r["tests_passing"] and r["branch_pushed"] for r in delivery_results)

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="delivery",
            data={"all_delivered": all_delivered},
        ))

    return {
        "delivery_results": delivery_results,
        "all_delivered": all_delivered,
        "current_stage": "delivery",
        "stage_history": [{"stage": "delivery", "status": "completed"}],
    }
