"""Worker entry point — executes the pipeline for a single repo within a CR.

Each worker handles exactly one repository. The Controller spawns one worker
per repo_url in the CR.

Usage: python -m hadron.worker.main --cr-id=CR-123 --repo-url=https://... [--repo-name=myrepo]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()  # read .env before anything else
from typing import Any

import structlog

from hadron.agent.prompt import PromptComposer
from hadron.config.bootstrap import load_bootstrap_config
from hadron.config.defaults import DEFAULT_MODEL, get_config_snapshot
from hadron.git.url import extract_repo_name
from hadron.models.events import EventType, PipelineEvent
from hadron.models.resume import pick_resume_node
from hadron.observability.logging import bind_contextvars, configure_logging
from hadron.observability.tracing import configure_tracing
from hadron.pipeline.graph import build_pipeline_graph
from hadron.worker.infra import WorkerInfra, connect
from hadron.worker.state import (
    build_initial_state,
    load_cr_and_mark_running,
    persist_failure,
    persist_result,
)

logger = structlog.stdlib.get_logger(__name__)


# ---------------------------------------------------------------------------
# Backwards-compatible aliases (private API, but used internally)
# ---------------------------------------------------------------------------

_connect = connect
_load_cr_and_mark_running = load_cr_and_mark_running
_build_initial_state = build_initial_state
_persist_result = persist_result
_persist_failure = persist_failure


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

# Maps stage_history stage names to graph node names
_STAGE_TO_NODE: dict[str, str] = {
    "intake": "intake",
    "repo_id": "repo_id",
    "worktree_setup": "worktree_setup",
    "behaviour_translation": "translation",
    "behaviour_verification": "verification",
    "implementation": "implementation",
    "review": "review",
    "rebase": "rebase",
    "delivery": "delivery",
    "release": "release",
}


def _find_resume_node(state_values: dict[str, Any]) -> str:
    """Find the last real pipeline node before 'paused' from stage_history.

    This is needed because 'paused' → END is terminal in the graph, so
    aupdate_state(as_node='paused') makes the graph think it's done.
    Instead we resume from the last real node so the conditional edge re-evaluates.
    """
    stage_history = state_values.get("stage_history", [])
    for entry in reversed(stage_history):
        stage = entry.get("stage", "")
        if stage != "paused" and stage in _STAGE_TO_NODE:
            return _STAGE_TO_NODE[stage]
    # Fallback: restart from translation (safe default for feedback loops)
    return "translation"


async def _execute_pipeline(
    infra: WorkerInfra,
    cfg: Any,
    cr_id: str,
    repo_name: str,
    initial_state: dict[str, Any],
    config_snapshot: dict[str, Any],
    prompt_composer: PromptComposer | None = None,
) -> dict[str, Any]:
    """Build, compile, and invoke the LangGraph pipeline. Returns final state."""
    graph = build_pipeline_graph()

    # Try to use postgres checkpointer
    checkpointer = None
    checkpointer_cm = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        checkpoint_url = cfg.postgres_url_sync.replace("+psycopg", "")
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(checkpoint_url)
        checkpointer = await checkpointer_cm.__aenter__()
        await checkpointer.setup()
    except (ImportError, ConnectionError, OSError, ValueError) as e:
        logger.warning("Failed to set up postgres checkpointer, running without: %s", e)
        checkpointer = None

    try:
        compiled = graph.compile(checkpointer=checkpointer)

        await infra.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_STARTED, stage="worker",
        ))

        pipeline_cfg = config_snapshot.get("pipeline", {})

        # E2E runner lifecycle — only wired in K8s mode. Local dev / tests keep
        # the subprocess path in pipeline.testing.run_test_command untouched.
        e2e_lifecycle = None
        if os.environ.get("HADRON_E2E_USE_K8S", "").lower() == "true":
            from hadron.pipeline.e2e_runner import E2ERunnerLifecycle
            e2e_lifecycle = E2ERunnerLifecycle(redis=infra.redis_client)

        runnable_config = {
            "configurable": {
                "thread_id": f"{cr_id}:{repo_name}",
                "event_bus": infra.event_bus,
                "intervention_manager": infra.intervention_mgr,
                "agent_backend": infra.agent_backend,
                "backend_pool": infra.backend_pool,
                "workspace_dir": cfg.workspace_dir,
                "model": pipeline_cfg.get("default_model", DEFAULT_MODEL),
                "explore_model": pipeline_cfg.get("explore_model", ""),
                "plan_model": pipeline_cfg.get("plan_model", ""),
                "stage_models": pipeline_cfg.get("stage_models", {}),
                "default_backend": pipeline_cfg.get("default_backend", "claude"),
                "redis": infra.redis_client,
                "prompt_composer": prompt_composer,
                "e2e_lifecycle": e2e_lifecycle,
            }
        }

        # Check for resume overrides (set by the /resume endpoint)
        state_overrides: dict | None = None
        override_key = f"hadron:cr:{cr_id}:resume_overrides"
        raw_overrides = await infra.redis_client.getdel(override_key)
        if raw_overrides:
            state_overrides = json.loads(raw_overrides)
            logger.info("Resume overrides for CR %s: %s", cr_id, state_overrides)

        # Determine whether a checkpoint already exists for this CR
        has_checkpoint = False
        if checkpointer:
            try:
                saved = await compiled.aget_state(runnable_config)
                has_checkpoint = saved.values is not None and len(saved.values) > 0
            except (ValueError, OSError, RuntimeError) as e:
                logger.debug("Failed to check for existing checkpoint: %s", e)
                has_checkpoint = False

        if has_checkpoint and state_overrides:
            resume_node = pick_resume_node(state_overrides)
            state_overrides.setdefault("status", "running")
            logger.info("Resuming CR %s from node '%s' with overrides", cr_id, resume_node)
            await compiled.aupdate_state(runnable_config, state_overrides, as_node=resume_node)
            return await compiled.ainvoke(None, config=runnable_config)
        elif has_checkpoint:
            # Find the last real node before "paused" to resume from its outgoing edge
            resume_from = _find_resume_node(saved.values)
            logger.info("Resuming CR %s from node '%s'", cr_id, resume_from)
            await compiled.aupdate_state(
                runnable_config, {"status": "running", "error": None}, as_node=resume_from,
            )
            return await compiled.ainvoke(None, config=runnable_config)
        else:
            if state_overrides:
                initial_state.update(state_overrides)
            return await compiled.ainvoke(initial_state, config=runnable_config)
    finally:
        if checkpointer_cm:
            await checkpointer_cm.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


class _RedisLogHandler(logging.Handler):
    """Logging handler that appends formatted log lines directly to Redis.

    This ensures worker logs reach the dashboard even if the controller
    process restarts and stops reading the subprocess stdout pipe.
    """

    def __init__(self, redis_client: Any, cr_id: str, repo_name: str) -> None:
        super().__init__()
        self._redis = redis_client
        self._key = f"hadron:cr:{cr_id}:{repo_name}:worker_log"
        self._loop: asyncio.AbstractEventLoop | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + "\n"
            loop = self._loop or asyncio.get_event_loop()
            self._loop = loop
            if loop.is_running():
                loop.create_task(self._write(msg))
            else:
                loop.run_until_complete(self._write(msg))
        except Exception:
            self.handleError(record)

    async def _write(self, msg: str) -> None:
        try:
            await self._redis.append(self._key, msg)
            await self._redis.expire(self._key, 86400)
        except Exception:
            pass


async def run_worker(cr_id: str, repo_url: str, repo_name: str = "", default_branch: str = "main") -> None:
    """Execute the pipeline for a single repo within a CR."""
    cfg = load_bootstrap_config()
    configure_logging(level=cfg.log_level, log_format=cfg.log_format)
    configure_tracing(
        enabled=cfg.otel_enabled,
        otlp_endpoint=cfg.otlp_endpoint,
        service_name="hadron-worker",
    )

    if not repo_name:
        repo_name = extract_repo_name(repo_url)

    bind_contextvars(cr_id=cr_id, repo_name=repo_name)

    safe_url = re.sub(r"://[^@]+@", "://***@", repo_url)
    logger.info("worker_starting", repo_url=safe_url)

    infra = connect(cfg)

    # Write logs directly to Redis so the dashboard works even if the
    # controller restarts and stops reading the subprocess stdout pipe.
    redis_log_key = f"hadron:cr:{cr_id}:{repo_name}:worker_log"
    await infra.redis_client.delete(redis_log_key)
    redis_handler = _RedisLogHandler(infra.redis_client, cr_id, repo_name)
    # Always emit JSON to Redis so the dashboard log viewer can parse entries
    redis_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    ))
    logging.getLogger().addHandler(redis_handler)

    try:
        cr_run = await load_cr_and_mark_running(infra, cr_id, repo_name)
        if cr_run is None:
            return

        initial_state = build_initial_state(cr_run, cr_id, repo_url, repo_name, default_branch)
        config_snapshot = cr_run.config_snapshot_json or get_config_snapshot()

        # Inject named OpenCode endpoints into the backend pool
        opencode_endpoints = config_snapshot.get("pipeline", {}).get("opencode_endpoints", [])
        if opencode_endpoints:
            infra.backend_pool.set_opencode_endpoints(opencode_endpoints)

        # Build PromptComposer from snapshot if available
        snapshot_prompts = config_snapshot.get("prompts")
        if snapshot_prompts:
            prompt_composer = PromptComposer.from_snapshot(snapshot_prompts)
        else:
            prompt_composer = PromptComposer()

        final_state = await _execute_pipeline(
            infra, cfg, cr_id, repo_name, initial_state, config_snapshot,
            prompt_composer=prompt_composer,
        )
        await persist_result(infra, cr_id, repo_name, final_state)

    except KeyboardInterrupt:
        logger.info("Worker interrupted for CR %s repo %s", cr_id, repo_name)
        raise
    except (RuntimeError, OSError, ConnectionError, ValueError, TypeError) as e:
        logger.exception("Worker failed for CR %s repo %s", cr_id, repo_name)
        await persist_failure(infra, cr_id, repo_name, e)
    except Exception as e:
        # Catch-all for truly unexpected errors (e.g. third-party library bugs).
        # Log at critical level so these stand out and can be narrowed further.
        logger.critical("Unexpected worker failure for CR %s repo %s: %s", cr_id, repo_name, type(e).__name__)
        logger.exception("Full traceback:")
        await persist_failure(infra, cr_id, repo_name, e)
    finally:
        logging.getLogger().removeHandler(redis_handler)
        await infra.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hadron pipeline worker")
    parser.add_argument("--cr-id", required=True, help="Change Request ID to process")
    parser.add_argument("--repo-url", required=True, help="Repository URL to process")
    parser.add_argument("--repo-name", default="", help="Repository name (derived from URL if omitted)")
    parser.add_argument("--default-branch", default="main", help="Default branch name")
    args = parser.parse_args()
    asyncio.run(run_worker(args.cr_id, args.repo_url, args.repo_name, args.default_branch))


if __name__ == "__main__":
    main()
