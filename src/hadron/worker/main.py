"""Worker entry point — executes the pipeline for a single CR.

Usage: python -m hadron.worker.main --cr-id=CR-123
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid

import redis.asyncio as aioredis
from sqlalchemy import select, update

from hadron.agent.claude import ClaudeAgentBackend
from hadron.agent.gemini import GeminiAgentBackend
from hadron.agent.provider_chain import BackendRegistry, ProviderChain, ProviderChainConfig
from hadron.config.bootstrap import load_bootstrap_config
from hadron.config.defaults import get_config_snapshot
from hadron.db.engine import create_engine, create_session_factory
from hadron.db.models import CRRun
from hadron.events.bus import RedisEventBus
from hadron.events.interventions import InterventionManager
from hadron.models.events import EventType, PipelineEvent
from hadron.pipeline.graph import build_pipeline_graph

logger = logging.getLogger(__name__)

# Maps override keys to the pipeline node they logically belong to.
# When resuming with overrides, the latest node in pipeline order is used as as_node.
OVERRIDE_NODE_MAP: dict[str, str] = {
    "rebase_clean": "rebase",
    "review_passed": "review",
    "behaviour_verified": "verification",
}

# Pipeline node execution order (used to pick the latest node from multiple overrides).
PIPELINE_NODE_ORDER: list[str] = [
    "intake", "repo_id", "worktree_setup", "translation", "verification",
    "tdd", "review", "rebase", "delivery", "release_gate", "release", "retrospective",
]


def _pick_resume_node(overrides: dict) -> str:
    """Pick the latest pipeline node that corresponds to the given overrides."""
    nodes = [OVERRIDE_NODE_MAP[k] for k in overrides if k in OVERRIDE_NODE_MAP]
    if not nodes:
        # Fallback: resume from the paused node (which is the last node before END)
        return "paused"
    # Return the node that appears latest in the pipeline
    return max(nodes, key=lambda n: PIPELINE_NODE_ORDER.index(n) if n in PIPELINE_NODE_ORDER else -1)


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
        agent_backend=get_backend(
            DEFAULT_MODEL,
            anthropic_api_key=cfg.anthropic_api_key,
            google_api_key=cfg.google_api_key,
        ),
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

        # Sync CRRun status: check if all repo workers are done.
        result = await session.execute(
            select(RepoRun.status).where(RepoRun.cr_id == cr_id)
        )
        all_statuses = [row[0] for row in result.fetchall()]
        terminal = {"completed", "failed", "paused"}
        if all(s in terminal for s in all_statuses):
            if all(s == "completed" for s in all_statuses):
                cr_status = "completed"
            elif any(s == "failed" for s in all_statuses):
                cr_status = "failed"
            else:
                cr_status = "paused"
            await session.execute(
                update(CRRun)
                .where(CRRun.cr_id == cr_id)
                .values(status=cr_status, error=final_state.get("error"))
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

    logger.info("Worker starting for CR %s", cr_id)

    # Connect to infrastructure
    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)

    event_bus = RedisEventBus(redis_client)
    intervention_mgr = InterventionManager(redis_client)

    # Build the provider chain (§9.3) — register all configured backends
    registry = BackendRegistry()
    if cfg.anthropic_api_key:
        registry.register(ClaudeAgentBackend(cfg.anthropic_api_key))
    if cfg.gemini_api_key:
        registry.register(GeminiAgentBackend(cfg.gemini_api_key))
    # Fallback: if no keys are set at all, register Claude anyway so the
    # pipeline can surface a clear API-key error rather than a chain error.
    if not registry.providers:
        registry.register(ClaudeAgentBackend())

    chain_order = get_config_snapshot().get("pipeline", {}).get("provider_chain", ["anthropic", "gemini"])
    agent_backend = ProviderChain(registry, ProviderChainConfig(chain=chain_order))

    try:
        # Load CR from database
        async with session_factory() as session:
            result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
            cr_run = result.scalar_one_or_none()

            if cr_run is None:
                logger.error("CR %s not found in database", cr_id)
                return

            # Update status to running
            await session.execute(
                update(CRRun).where(CRRun.cr_id == cr_id).values(status="running")
            )
            await session.commit()

        # Build initial state
        raw_cr = cr_run.raw_cr_json or {}
        config_snapshot = cr_run.config_snapshot_json or get_config_snapshot()

        initial_state = {
            "cr_id": cr_id,
            "source": cr_run.source,
            "external_id": cr_run.external_id or "",
            "raw_cr_title": raw_cr.get("title", ""),
            "raw_cr_text": raw_cr.get("description", ""),
            "affected_repos": [{
                "repo_url": raw_cr.get("repo_url", ""),
                "repo_name": raw_cr.get("repo_url", "").rstrip("/").split("/")[-1] if raw_cr.get("repo_url") else "",
                "default_branch": raw_cr.get("repo_default_branch", "main"),
                "test_command": raw_cr.get("test_command", "pytest"),
                "language": raw_cr.get("language", "python"),
            }],
            "config_snapshot": config_snapshot,
            "status": "running",
            "cost_input_tokens": 0,
            "cost_output_tokens": 0,
            "cost_usd": 0.0,
            "stage_history": [],
        }

        # Build and run graph
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
        except Exception as e:
            logger.warning("Failed to set up postgres checkpointer, running without: %s", e)
            checkpointer = None

        try:
            compiled = graph.compile(checkpointer=checkpointer)

            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.PIPELINE_STARTED, stage="worker",
            ))

            # Run the graph
            runnable_config = {
                "configurable": {
                    "thread_id": cr_id,
                    "event_bus": event_bus,
                    "intervention_manager": intervention_mgr,
                    "agent_backend": agent_backend,
                    "workspace_dir": cfg.workspace_dir,
                    "model": config_snapshot.get("pipeline", {}).get("default_model", "gemini-3-pro-preview"),
                    "redis": redis_client,
                }
            }

            # Check for resume overrides (set by the /resume endpoint)
            state_overrides: dict | None = None
            override_key = f"hadron:cr:{cr_id}:resume_overrides"
            raw_overrides = await redis_client.getdel(override_key)
            if raw_overrides:
                state_overrides = json.loads(raw_overrides)
                logger.info("Resume overrides for CR %s: %s", cr_id, state_overrides)

            # Determine whether a checkpoint already exists for this CR
            has_checkpoint = False
            if checkpointer:
                try:
                    saved = await compiled.aget_state(runnable_config)
                    has_checkpoint = saved.values is not None and len(saved.values) > 0
                except Exception:
                    has_checkpoint = False

            if has_checkpoint and state_overrides:
                # Resume from checkpoint with state overrides applied
                resume_node = _pick_resume_node(state_overrides)
                logger.info("Resuming CR %s from node '%s' with overrides", cr_id, resume_node)
                await compiled.aupdate_state(runnable_config, state_overrides, as_node=resume_node)
                final_state = await compiled.ainvoke(None, config=runnable_config)
            elif has_checkpoint:
                # Resume from checkpoint without overrides
                logger.info("Resuming CR %s from existing checkpoint", cr_id)
                final_state = await compiled.ainvoke(None, config=runnable_config)
            else:
                # Fresh run — merge any overrides into initial state
                if state_overrides:
                    initial_state.update(state_overrides)
                final_state = await compiled.ainvoke(initial_state, config=runnable_config)
        finally:
            if checkpointer_cm:
                await checkpointer_cm.__aexit__(None, None, None)

        # Update CR run status
        final_status = final_state.get("status", "completed")
        final_cost = final_state.get("cost_usd", 0.0)

        async with session_factory() as session:
            await session.execute(
                update(CRRun)
                .where(CRRun.cr_id == cr_id)
                .values(
                    status=final_status,
                    cost_usd=final_cost,
                    error=final_state.get("error"),
                )
            )
            await session.commit()

        # Emit terminal event so the frontend updates status
        if final_status == "paused":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.PIPELINE_PAUSED, stage="worker",
                data={"error": final_state.get("error", "")},
            ))
        elif final_status == "completed":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.PIPELINE_COMPLETED, stage="worker",
                data={"cost_usd": final_cost},
            ))
        elif final_status == "failed":
            await event_bus.emit(PipelineEvent(
                cr_id=cr_id, event_type=EventType.PIPELINE_FAILED, stage="worker",
                data={"error": final_state.get("error", "")},
            ))

        logger.info("Worker completed for CR %s with status=%s cost=$%.4f", cr_id, final_status, final_cost)

    except Exception as e:
        logger.exception("Worker failed for CR %s", cr_id)
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_FAILED, stage="worker",
            data={"error": str(e)},
        ))
        async with session_factory() as session:
            await session.execute(
                update(CRRun)
                .where(CRRun.cr_id == cr_id)
                .values(status="failed", error=str(e))
            )
            await session.commit()
    finally:
        await redis_client.aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hadron pipeline worker")
    parser.add_argument("--cr-id", required=True, help="Change Request ID to process")
    args = parser.parse_args()
    asyncio.run(run_worker(args.cr_id))


if __name__ == "__main__":
    main()
