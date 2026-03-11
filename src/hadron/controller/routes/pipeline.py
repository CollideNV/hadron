"""Pipeline status and intervention routes."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select, update

from hadron.controller.dependencies import (
    get_event_bus,
    get_intervention_mgr,
    get_job_spawner,
    get_redis,
    get_session_factory,
)
from hadron.db.models import CRRun, RepoRun
from hadron.events.bus import EventBus
from hadron.events.interventions import InterventionManager
from hadron.models.events import EventType, PipelineEvent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline"])


def _extract_title(cr_run: CRRun) -> str:
    """Extract title from raw_cr_json."""
    if cr_run.raw_cr_json and isinstance(cr_run.raw_cr_json, dict):
        return cr_run.raw_cr_json.get("title", "")
    return ""


@router.get("/pipeline/list")
async def list_pipelines(
    session_factory: Any = Depends(get_session_factory),
) -> list[dict]:
    """List all pipeline runs, ordered by creation time (newest first)."""
    async with session_factory() as session:
        result = await session.execute(
            select(CRRun).order_by(CRRun.created_at.desc()).limit(100)
        )
        runs = result.scalars().all()
        return [
            {
                "cr_id": r.cr_id,
                "title": _extract_title(r),
                "status": r.status,
                "source": r.source,
                "external_id": r.external_id,
                "cost_usd": r.cost_usd,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in runs
        ]


@router.get("/pipeline/{cr_id}")
async def get_pipeline_status(
    cr_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> dict:
    """Get the current status of a pipeline run, including per-repo worker status."""
    async with session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = result.scalar_one_or_none()
        if not cr_run:
            raise HTTPException(status_code=404, detail="CR not found")

        repo_result = await session.execute(
            select(RepoRun).where(RepoRun.cr_id == cr_id)
        )
        repo_runs = repo_result.scalars().all()

        return {
            "cr_id": cr_run.cr_id,
            "title": _extract_title(cr_run),
            "status": cr_run.status,
            "source": cr_run.source,
            "external_id": cr_run.external_id,
            "cost_usd": cr_run.cost_usd,
            "error": cr_run.error,
            "created_at": cr_run.created_at.isoformat() if cr_run.created_at else None,
            "updated_at": cr_run.updated_at.isoformat() if cr_run.updated_at else None,
            "repos": [
                {
                    "repo_name": rr.repo_name,
                    "repo_url": rr.repo_url,
                    "status": rr.status,
                    "branch_name": rr.branch_name,
                    "pr_url": rr.pr_url,
                    "cost_usd": rr.cost_usd,
                    "error": rr.error,
                }
                for rr in repo_runs
            ],
        }


class InterventionRequest(BaseModel):
    instructions: str


@router.post("/pipeline/{cr_id}/intervene")
async def set_intervention(
    cr_id: str,
    body: InterventionRequest,
    session_factory: Any = Depends(get_session_factory),
    intervention_mgr: InterventionManager = Depends(get_intervention_mgr),
) -> dict:
    """Set a human intervention for a running pipeline."""
    async with session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="CR not found")

    await intervention_mgr.set_intervention(cr_id, body.instructions)
    return {"status": "intervention_set", "cr_id": cr_id}


class ResumeRequest(BaseModel):
    state_overrides: dict[str, object] = {}


@router.post("/pipeline/{cr_id}/resume")
async def resume_pipeline(
    cr_id: str,
    body: ResumeRequest,
    session_factory: Any = Depends(get_session_factory),
    redis: Any = Depends(get_redis),
    spawner: Any = Depends(get_job_spawner),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict:
    """Resume a paused or failed pipeline, optionally overriding state."""
    async with session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = result.scalar_one_or_none()
        if not cr_run:
            raise HTTPException(status_code=404, detail="CR not found")
        if cr_run.status not in ("paused", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"CR is '{cr_run.status}', can only resume paused or failed runs",
            )

    # Store overrides in Redis with 1h TTL so the worker can pick them up
    if body.state_overrides:
        override_key = f"hadron:cr:{cr_id}:resume_overrides"
        await redis.set(override_key, json.dumps(body.state_overrides), ex=3600)

    # Find repos to resume BEFORE updating status
    async with session_factory() as session:
        repo_result = await session.execute(
            select(RepoRun).where(
                RepoRun.cr_id == cr_id,
                RepoRun.status.in_(("paused", "failed")),
            )
        )
        repos_to_resume = repo_result.scalars().all()

    # Now update DB status to running
    async with session_factory() as session:
        await session.execute(
            update(CRRun).where(CRRun.cr_id == cr_id).values(status="running", error=None)
        )
        if repos_to_resume:
            await session.execute(
                update(RepoRun)
                .where(RepoRun.cr_id == cr_id, RepoRun.status.in_(("paused", "failed")))
                .values(status="running", error=None)
            )
        await session.commit()

    for rr in repos_to_resume:
        await spawner.spawn(
            cr_id, repo_url=rr.repo_url, repo_name=rr.repo_name,
        )

    # Emit event so dashboard updates
    await event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.PIPELINE_RESUMED,
        stage="controller",
        data={"overrides": body.state_overrides},
    ))

    return {"status": "resumed", "cr_id": cr_id, "overrides": body.state_overrides}


class NudgeRequest(BaseModel):
    role: str
    message: str


@router.post("/pipeline/{cr_id}/nudge")
async def send_nudge(
    cr_id: str,
    body: NudgeRequest,
    session_factory: Any = Depends(get_session_factory),
    intervention_mgr: InterventionManager = Depends(get_intervention_mgr),
) -> dict:
    """Send a nudge to a specific agent role in a running pipeline."""
    async with session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="CR not found")

    await intervention_mgr.set_nudge(cr_id, body.role, body.message)
    return {"status": "nudge_set", "cr_id": cr_id, "role": body.role}


@router.get("/pipeline/{cr_id}/conversation")
async def get_conversation(
    cr_id: str,
    key: str,
    redis: Any = Depends(get_redis),
) -> list:
    """Retrieve a stored agent conversation from Redis."""
    if not key.startswith(f"hadron:cr:{cr_id}:conv:"):
        raise HTTPException(status_code=400, detail="Invalid conversation key")

    data = await redis.get(key)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversation not found or expired")

    raw = data.decode() if isinstance(data, bytes) else data
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse conversation data")


@router.get("/pipeline/{cr_id}/logs")
async def get_worker_logs(
    cr_id: str,
    redis: Any = Depends(get_redis),
    session_factory: Any = Depends(get_session_factory),
) -> PlainTextResponse:
    """Retrieve worker logs for a CR (merges all repo worker logs)."""
    # Collect logs from all repo workers for this CR
    async with session_factory() as session:
        result = await session.execute(
            select(RepoRun.repo_name).where(RepoRun.cr_id == cr_id)
        )
        repo_names = [r[0] for r in result.all()]

    parts: list[str] = []
    for repo_name in repo_names:
        key = f"hadron:cr:{cr_id}:{repo_name}:worker_log"
        data = await redis.get(key)
        if data:
            text = data.decode(errors="replace") if isinstance(data, bytes) else data
            if repo_names and len(repo_names) > 1:
                parts.append(f"=== {repo_name} ===\n{text}")
            else:
                parts.append(text)

    if not parts:
        return PlainTextResponse("No logs available for this CR.", status_code=200)

    return PlainTextResponse("\n".join(parts))
