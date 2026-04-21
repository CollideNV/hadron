"""E2E Testing node — run and maintain end-to-end tests."""

from __future__ import annotations

import shutil
from typing import Any

import structlog

from hadron.agent.base import CostAccumulator
from hadron.config.limits import E2E_TEST_TIMEOUT_SECONDS, MAX_E2E_RETRIES, TEST_OUTPUT_BRIEF_CHARS, TEST_OUTPUT_EVENT_CHARS
from hadron.models.events import EventType, PipelineEvent
from hadron.models.pipeline_state import PipelineState
from hadron.pipeline.nodes import NodeContext, RepoInfo, pipeline_node, run_agent
from hadron.pipeline.nodes.cr_format import format_cr_section
from hadron.pipeline.nodes.diff_capture import emit_stage_diff
from hadron.pipeline.testing import _find_free_port, run_test_command
from hadron.security.validators import validate_e2e_setup_command, validate_test_command


async def _run_e2e(
    ctx: NodeContext,
    ri: RepoInfo,
    cr_id: str,
    command: str,
    env: dict[str, str],
    timeout: int,
) -> tuple[bool, str]:
    """Route E2E execution through the runner pod when in K8s mode.

    Subprocess path stays live for local dev and the dummy_server flow.
    """
    if not validate_test_command(command):
        return False, f"E2E command rejected by validator: {command}"

    if ctx.e2e_lifecycle:
        from hadron.pipeline.e2e_runner import build_e2e_contract
        contract = build_e2e_contract(
            worktree_path=ri.worktree_path,
            command=command,
            env=env,
            timeout=timeout,
            languages=ri.languages,
        )
        # Validate setup steps before submission
        for step in contract.setup:
            if not validate_e2e_setup_command(step):
                return False, f"E2E setup step rejected by validator: {step}"
        return await ctx.e2e_lifecycle.submit(
            cr_id, ri.repo_name, contract,
        )
    return await run_test_command(
        ri.worktree_path, command, cr_id, timeout=timeout, extra_env=env,
    )

logger = structlog.stdlib.get_logger(__name__)


@pipeline_node("e2e_testing")
async def e2e_testing_node(state: PipelineState, ctx: NodeContext, cr_id: str) -> dict[str, Any]:
    """Run E2E tests and use an agent to fix/expand them if needed.

    Flow:
    1. Run existing E2E tests
    2. If tests fail or to expand coverage: run agent with e2e_testing role
    3. Re-run E2E tests after agent modifications
    4. Commit E2E test changes
    """
    composer = ctx.prompt_composer
    structured_cr = state.get("structured_cr", {})
    costs = CostAccumulator()

    ri = RepoInfo.from_state(state)

    if not ri.e2e_test_commands:
        # Shouldn't happen due to conditional edge, but defensive
        logger.info("e2e_skipped", reason="no_commands")
        return {
            "e2e_results": [{"repo_name": ri.repo_name, "tests_passing": True, "test_output": "skipped"}],
            "e2e_passed": True,
            "current_stage": "e2e_testing",
            "stage_history": [{"stage": "e2e_testing", "status": "completed"}],
        }

    e2e_command = ri.e2e_test_commands[0]

    # In subprocess mode (no K8s runner), verify that the browser runtime
    # is available.  If not, skip gracefully instead of letting the agent
    # burn rounds on an environment issue it cannot fix.
    if not ctx.e2e_lifecycle:
        _needs_playwright = any(kw in e2e_command for kw in ("playwright", "cypress"))
        if _needs_playwright and not shutil.which("npx"):
            logger.warning("e2e_skipped", reason="npx_not_found", command=e2e_command)
            return {
                "e2e_results": [{"repo_name": ri.repo_name, "tests_passing": True,
                                 "test_output": "skipped: npx not available in worker environment"}],
                "e2e_passed": True,
                "current_stage": "e2e_testing",
                "stage_history": [{"stage": "e2e_testing", "status": "completed"}],
            }
        if _needs_playwright:
            # Check if Playwright browsers are actually installed
            import asyncio as _asyncio
            _check = await _asyncio.create_subprocess_exec(
                "npx", "playwright", "install", "--dry-run",
                stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.STDOUT,
            )
            _out, _ = await _check.communicate()
            # If dry-run fails or output mentions "missing", browsers aren't installed
            if _check.returncode != 0 or b"Executable doesn't exist" in _out or b"missing" in _out.lower():
                logger.warning("e2e_skipped", reason="browsers_not_installed", command=e2e_command)
                await ctx.event_bus.emit(PipelineEvent(
                    cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="e2e_testing",
                    data={"skipped": True, "reason": "Playwright browsers not installed in worker — use K8s E2E runner"},
                ))
                return {
                    "e2e_results": [{"repo_name": ri.repo_name, "tests_passing": True,
                                     "test_output": "skipped: Playwright browsers not installed in worker environment. "
                                                    "Set HADRON_E2E_USE_K8S=true to use the dedicated E2E runner pod."}],
                    "e2e_passed": True,
                    "current_stage": "e2e_testing",
                    "stage_history": [{"stage": "e2e_testing", "status": "completed"}],
                }

    # Port allocation:
    # - Subprocess mode: pick free ports on the worker host so concurrent
    #   workers don't collide.
    # - K8s mode: the runner pod has its own network namespace, so fixed
    #   ports are safe and detection logic in build_e2e_contract can key off
    #   HADRON_TEST_BACKEND_PORT.
    if ctx.e2e_lifecycle:
        # Use the same defaults as playwright.config.ts and vite.config.ts
        # so that the Vite proxy (hardcoded to localhost:8000) matches the
        # dummy_server port. The runner pod has its own network namespace
        # so fixed ports are safe.
        e2e_env = {
            "HADRON_TEST_BACKEND_PORT": "8000",
            "HADRON_TEST_FRONTEND_PORT": "5173",
        }
    else:
        e2e_env = {
            "HADRON_TEST_BACKEND_PORT": str(_find_free_port()),
            "HADRON_TEST_FRONTEND_PORT": str(_find_free_port()),
        }
    logger.info("e2e_starting", backend_port=e2e_env["HADRON_TEST_BACKEND_PORT"],
                frontend_port=e2e_env["HADRON_TEST_FRONTEND_PORT"])

    max_retries = (
        state.get("config_snapshot", {})
        .get("pipeline", {})
        .get("max_e2e_retries", MAX_E2E_RETRIES)
    )

    # Initial E2E test run
    tests_passing, test_output = await _run_e2e(
        ctx, ri, cr_id, e2e_command, e2e_env, E2E_TEST_TIMEOUT_SECONDS,
    )

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.TEST_RUN, stage="e2e_testing",
        data={
            "repo": ri.repo_name,
            "passed": tests_passing,
            "output_tail": test_output[-TEST_OUTPUT_EVENT_CHARS:],
        },
    ))

    # Re-run agent on failure (up to max_retries), accumulating costs
    for attempt in range(max_retries + 1):
        if tests_passing and attempt > 0:
            break

        repo_context = composer.build_repo_context(
            agents_md=ri.agents_md,
            directory_tree=state.get("directory_tree", ""),
            languages=ri.languages,
            test_commands=ri.test_commands,
        )

        cr_text = format_cr_section(structured_cr)
        system_prompt = composer.compose_system_prompt("e2e_testing", repo_context)

        payload = cr_text
        payload += f"\n\n## E2E Test Command\n\n`{e2e_command}`\n"
        if not tests_passing:
            payload += f"\n## E2E Test Failures\n\n```\n{test_output[-TEST_OUTPUT_BRIEF_CHARS:]}\n```\n"

        user_prompt = composer.compose_user_prompt(payload)

        agent_run = await run_agent(
            ctx,
            role="e2e_testing",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cr_id=cr_id,
            stage="e2e_testing",
            repo_name=ri.repo_name,
            working_directory=ri.worktree_path,
            loop_iteration=attempt,
            explore_model="",   # Skip explore phase
            plan_model="",      # Skip plan phase
        )
        costs.add(agent_run.result)

        # Re-run E2E tests after agent modifications
        tests_passing, test_output = await _run_e2e(
            ctx, ri, cr_id, e2e_command, e2e_env, E2E_TEST_TIMEOUT_SECONDS,
        )

        await ctx.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.TEST_RUN, stage="e2e_testing",
            data={
                "repo": ri.repo_name,
                "passed": tests_passing,
                "output_tail": test_output[-TEST_OUTPUT_EVENT_CHARS:],
            },
        ))

    # Commit E2E test changes
    await ctx.worktree_manager.commit(
        ri.worktree_path,
        f"test: e2e tests for {cr_id} ({'green' if tests_passing else 'red'})",
    )

    # Emit diff of E2E test changes
    await emit_stage_diff(
        ctx.event_bus, cr_id, "e2e_testing", ri.repo_name,
        ctx.worktree_manager, ri.worktree_path, ri.default_branch,
    )

    e2e_result = {
        "repo_name": ri.repo_name,
        "tests_passing": tests_passing,
        "test_output": test_output[-TEST_OUTPUT_BRIEF_CHARS:],
    }

    await ctx.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.STAGE_COMPLETED, stage="e2e_testing",
        data={"all_passing": tests_passing},
    ))

    return {
        "e2e_results": [e2e_result],
        "e2e_passed": tests_passing,
        "current_stage": "e2e_testing",
        **costs.to_state_dict(),
        "stage_history": [{"stage": "e2e_testing", "status": "completed"}],
    }
