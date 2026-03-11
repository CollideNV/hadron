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
import re
import sys
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select, update

from hadron.agent.claude import ClaudeAgentBackend
from hadron.config.bootstrap import load_bootstrap_config
from hadron.config.defaults import BRANCH_PREFIX, DEFAULT_MODEL, get_config_snapshot
from hadron.db.engine import create_engine, create_session_factory
from hadron.db.models import CRRun, RepoRun
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager
from hadron.git.url import extract_repo_name
from hadron.models.events import EventType, PipelineEvent
from hadron.models.resume import pick_resume_node
from hadron.pipeline.graph import build_pipeline_graph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker infrastructure
# ---------------------------------------------------------------------------


@dataclass
class WorkerInfra:
    """Infrastructure connections for a worker run."""

    engine: Any
    session_factory: Any
    redis_client: aioredis.Redis
    event_bus: RedisEventBus
    intervention_mgr: InterventionManager
    agent_backend: ClaudeAgentBackend

    async def close(self) -> None:
        await self.redis_client.aclose()
        await self.engine.dispose()


def _connect(cfg: Any) -> WorkerInfra:
    """Create all infrastructure connections from bootstrap config."""
    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)
    return WorkerInfra(
        engine=engine,
        session_factory=session_factory,
        redis_client=redis_client,
        event_bus=RedisEventBus(redis_client),
        intervention_mgr=InterventionManager(redis_client),
        agent_backend=ClaudeAgentBackend(cfg.anthropic_api_key),
    )


# ---------------------------------------------------------------------------
# State loading
# ---------------------------------------------------------------------------


async def _load_cr_and_mark_running(
    infra: WorkerInfra, cr_id: str, repo_name: str,
) -> CRRun | None:
    """Load the CRRun from the database and mark the RepoRun as running."""
    async with infra.session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = result.scalar_one_or_none()

        if cr_run is None:
            logger.error("CR %s not found in database", cr_id)
            return None

        await session.execute(
            update(RepoRun)
            .where(RepoRun.cr_id == cr_id, RepoRun.repo_name == repo_name)
            .values(status="running")
        )
        await session.execute(
            update(CRRun)
            .where(CRRun.cr_id == cr_id, CRRun.status == "pending")
            .values(status="running")
        )
        await session.commit()
    return cr_run


def _build_initial_state(
    cr_run: CRRun, cr_id: str, repo_url: str, repo_name: str, default_branch: str,
) -> dict[str, Any]:
    """Build the initial PipelineState dict from a CRRun record."""
    raw_cr = cr_run.raw_cr_json or {}
    config_snapshot = cr_run.config_snapshot_json or get_config_snapshot()
    return {
        "cr_id": cr_id,
        "source": cr_run.source,
        "external_id": cr_run.external_id or "",
        "raw_cr_title": raw_cr.get("title", ""),
        "raw_cr_text": raw_cr.get("description", ""),
        "repo": {
            "repo_url": repo_url,
            "repo_name": repo_name,
            "default_branch": default_branch,
        },
        "config_snapshot": config_snapshot,
        "status": "running",
        "cost_input_tokens": 0,
        "cost_output_tokens": 0,
        "cost_usd": 0.0,
        "stage_history": [],
    }


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------


async def _persist_result(
    infra: WorkerInfra, cr_id: str, repo_name: str, final_state: dict[str, Any],
) -> None:
    """Write final pipeline state to the database and emit terminal events."""
    final_status = final_state.get("status", "completed")
    final_cost = final_state.get("cost_usd", 0.0)

    release_results = final_state.get("release_results", [])
    pr_description = ""
    if release_results:
        pr_description = release_results[0].get("pr_description", "")

    async with infra.session_factory() as session:
        await session.execute(
            update(RepoRun)
            .where(RepoRun.cr_id == cr_id, RepoRun.repo_name == repo_name)
            .values(
                status=final_status,
                cost_usd=final_cost,
                pr_description=pr_description,
                branch_name=f"{BRANCH_PREFIX}{cr_id}",
                error=final_state.get("error"),
            )
        )
        await session.commit()

    event_data = {"repo": repo_name, "cost_usd": final_cost}
    if final_status == "paused":
        await infra.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_PAUSED, stage="worker",
            data={**event_data, "error": final_state.get("error", "")},
        ))
    elif final_status == "completed":
        await infra.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_COMPLETED, stage="worker",
            data=event_data,
        ))
    elif final_status == "failed":
        await infra.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_FAILED, stage="worker",
            data={**event_data, "error": final_state.get("error", "")},
        ))

    logger.info(
        "Worker completed for CR %s repo %s with status=%s cost=$%.4f",
        cr_id, repo_name, final_status, final_cost,
    )


async def _persist_failure(
    infra: WorkerInfra, cr_id: str, repo_name: str, error: Exception,
) -> None:
    """Record an unhandled worker failure in the database and event bus."""
    await infra.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.PIPELINE_FAILED, stage="worker",
        data={"repo": repo_name, "error": str(error)},
    ))
    async with infra.session_factory() as session:
        await session.execute(
            update(RepoRun)
            .where(RepoRun.cr_id == cr_id, RepoRun.repo_name == repo_name)
            .values(status="failed", error=str(error))
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


async def _execute_pipeline(
    infra: WorkerInfra,
    cfg: Any,
    cr_id: str,
    repo_name: str,
    initial_state: dict[str, Any],
    config_snapshot: dict[str, Any],
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
        runnable_config = {
            "configurable": {
                "thread_id": f"{cr_id}:{repo_name}",
                "event_bus": infra.event_bus,
                "intervention_manager": infra.intervention_mgr,
                "agent_backend": infra.agent_backend,
                "workspace_dir": cfg.workspace_dir,
                "model": pipeline_cfg.get("default_model", DEFAULT_MODEL),
                "explore_model": pipeline_cfg.get("explore_model", ""),
                "plan_model": pipeline_cfg.get("plan_model", ""),
                "redis": infra.redis_client,
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
            logger.info("Resuming CR %s from node '%s' with overrides", cr_id, resume_node)
            await compiled.aupdate_state(runnable_config, state_overrides, as_node=resume_node)
            return await compiled.ainvoke(None, config=runnable_config)
        elif has_checkpoint:
            logger.info("Resuming CR %s from existing checkpoint", cr_id)
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


async def run_worker(cr_id: str, repo_url: str, repo_name: str = "", default_branch: str = "main") -> None:
    """Execute the pipeline for a single repo within a CR."""
    cfg = load_bootstrap_config()
    logging.basicConfig(level=getattr(logging, cfg.log_level), format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if not repo_name:
        repo_name = extract_repo_name(repo_url)

    safe_url = re.sub(r"://[^@]+@", "://***@", repo_url)
    logger.info("Worker starting for CR %s, repo %s (%s)", cr_id, repo_name, safe_url)

    infra = _connect(cfg)
    try:
        cr_run = await _load_cr_and_mark_running(infra, cr_id, repo_name)
        if cr_run is None:
            return

        initial_state = _build_initial_state(cr_run, cr_id, repo_url, repo_name, default_branch)
        config_snapshot = cr_run.config_snapshot_json or get_config_snapshot()

        final_state = await _execute_pipeline(
            infra, cfg, cr_id, repo_name, initial_state, config_snapshot,
        )
        await _persist_result(infra, cr_id, repo_name, final_state)

    except KeyboardInterrupt:
        logger.info("Worker interrupted for CR %s repo %s", cr_id, repo_name)
        raise
    except (RuntimeError, OSError, ConnectionError, ValueError, TypeError) as e:
        logger.exception("Worker failed for CR %s repo %s", cr_id, repo_name)
        await _persist_failure(infra, cr_id, repo_name, e)
    except Exception as e:
        # Catch-all for truly unexpected errors (e.g. third-party library bugs).
        # Log at critical level so these stand out and can be narrowed further.
        logger.critical("Unexpected worker failure for CR %s repo %s: %s", cr_id, repo_name, type(e).__name__)
        logger.exception("Full traceback:")
        await _persist_failure(infra, cr_id, repo_name, e)
    finally:
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
