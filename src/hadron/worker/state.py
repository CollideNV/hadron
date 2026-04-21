"""Worker state management — CR loading, initial state building, and result persistence."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select, update

from hadron.config.defaults import BRANCH_PREFIX, get_config_snapshot
from hadron.db.models import CRRun, RepoRun, RunSummary
from hadron.models.events import EventType, PipelineEvent
from hadron.observability.metrics import publish_worker_metrics
from hadron.observability.retrospective import generate_retrospective
from hadron.observability.summary import build_run_summary
from hadron.worker.infra import WorkerInfra

logger = structlog.stdlib.get_logger(__name__)


async def load_cr_and_mark_running(
    infra: WorkerInfra, cr_id: str, repo_name: str,
) -> CRRun | None:
    """Load the CRRun from the database and mark the RepoRun as running."""
    async with infra.session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = result.scalar_one_or_none()

        if cr_run is None:
            logger.error("cr_not_found", cr_id=cr_id)
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


def build_initial_state(
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


async def persist_result(
    infra: WorkerInfra, cr_id: str, repo_name: str, final_state: dict[str, Any],
) -> None:
    """Write final pipeline state to the database and emit terminal events."""
    final_status = final_state.get("status", "completed")
    final_cost = final_state.get("cost_usd", 0.0)

    release_results = final_state.get("release_results", [])
    pr_description = ""
    pr_url = ""
    if release_results:
        pr_description = release_results[0].get("pr_description", "")
        pr_url = release_results[0].get("pr_url", "")

    summary_dict = build_run_summary(cr_id, repo_name, final_state)
    retrospective = generate_retrospective(summary_dict)
    summary_dict["retrospective_json"] = retrospective

    async with infra.session_factory() as session:
        await session.execute(
            update(RepoRun)
            .where(RepoRun.cr_id == cr_id, RepoRun.repo_name == repo_name)
            .values(
                status=final_status,
                cost_usd=final_cost,
                pr_url=pr_url or None,
                pr_description=pr_description,
                branch_name=f"{BRANCH_PREFIX}{cr_id}",
                error=final_state.get("error"),
            )
        )
        # Sync CRRun status so resume/UI reflects the actual state
        await session.execute(
            update(CRRun)
            .where(CRRun.cr_id == cr_id)
            .values(
                status=final_status,
                cost_usd=final_cost,
                error=final_state.get("error"),
                pause_reason=final_state.get("pause_reason"),
            )
        )
        session.add(RunSummary(**summary_dict))
        await session.commit()

    try:
        await publish_worker_metrics(infra.redis_client, {
            "status": "failed",
            "cr_id": cr_id,
            "repo_name": repo_name,
        })
    except Exception:
        logger.debug("metrics_publish_failed", phase="failure")
    await infra.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.RETROSPECTIVE, stage="retrospective",
        data={"repo": repo_name, "insights": retrospective},
    ))

    event_data = {"repo": repo_name, "cost_usd": final_cost}
    if final_status == "paused":
        await infra.event_bus.emit(PipelineEvent(
            cr_id=cr_id, event_type=EventType.PIPELINE_PAUSED, stage="worker",
            data={
                **event_data,
                "reason": final_state.get("pause_reason", "unknown"),
                "error": final_state.get("error", ""),
            },
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

    # Publish metrics to controller via Redis pub/sub
    try:
        await publish_worker_metrics(infra.redis_client, {
            "status": final_status,
            "cr_id": cr_id,
            "repo_name": repo_name,
            "cost_usd": final_cost,
        })
    except Exception:
        logger.debug("metrics_publish_failed", phase="completion")

    logger.info(
        "worker_completed",
        cr_id=cr_id,
        repo_name=repo_name,
        status=final_status,
        cost_usd=final_cost,
    )


async def persist_failure(
    infra: WorkerInfra, cr_id: str, repo_name: str, error: Exception,
) -> None:
    """Record an unhandled worker failure in the database and event bus."""
    await infra.event_bus.emit(PipelineEvent(
        cr_id=cr_id, event_type=EventType.PIPELINE_FAILED, stage="worker",
        data={"repo": repo_name, "error": str(error)},
    ))
    failure_state: dict[str, Any] = {
        "status": "failed",
        "error": str(error),
    }
    summary_dict = build_run_summary(cr_id, repo_name, failure_state)
    retrospective = generate_retrospective(summary_dict)
    summary_dict["retrospective_json"] = retrospective

    async with infra.session_factory() as session:
        await session.execute(
            update(RepoRun)
            .where(RepoRun.cr_id == cr_id, RepoRun.repo_name == repo_name)
            .values(status="failed", error=str(error))
        )
        await session.execute(
            update(CRRun)
            .where(CRRun.cr_id == cr_id)
            .values(status="failed", error=str(error))
        )
        session.add(RunSummary(**summary_dict))
        await session.commit()
