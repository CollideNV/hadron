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


async def run_worker(cr_id: str) -> None:
    """Execute the pipeline for a single CR."""
    cfg = load_bootstrap_config()
    logging.basicConfig(level=getattr(logging, cfg.log_level), format="%(asctime)s %(name)s %(levelname)s %(message)s")

    logger.info("Worker starting for CR %s", cr_id)

    # Connect to infrastructure
    engine = create_engine(cfg.postgres_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.from_url(cfg.redis_url)

    event_bus = RedisEventBus(redis_client)
    intervention_mgr = InterventionManager(redis_client)
    agent_backend = ClaudeAgentBackend(cfg.anthropic_api_key)

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
            pipeline_cfg = config_snapshot.get("pipeline", {})
            runnable_config = {
                "configurable": {
                    "thread_id": cr_id,
                    "event_bus": event_bus,
                    "intervention_manager": intervention_mgr,
                    "agent_backend": agent_backend,
                    "workspace_dir": cfg.workspace_dir,
                    "model": pipeline_cfg.get("default_model", "claude-sonnet-4-20250514"),
                    "explore_model": pipeline_cfg.get("explore_model", ""),
                    "plan_model": pipeline_cfg.get("plan_model", ""),
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
