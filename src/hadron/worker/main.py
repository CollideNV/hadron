"""Worker entry point — executes the pipeline for a single CR.

Usage: python -m hadron.worker.main --cr-id=CR-123
"""

from __future__ import annotations

import argparse
import asyncio
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
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            checkpointer = AsyncPostgresSaver.from_conn_string(cfg.postgres_url_sync)
            await checkpointer.setup()
        except Exception as e:
            logger.warning("Failed to set up postgres checkpointer, running without: %s", e)

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
                "model": config_snapshot.get("pipeline", {}).get("default_model", "claude-sonnet-4-20250514"),
            }
        }

        final_state = await compiled.ainvoke(initial_state, config=runnable_config)

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
