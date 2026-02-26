"""Pipeline status and intervention routes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select, update

from hadron.db.models import CRRun
from hadron.models.events import EventType, PipelineEvent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline"])


def _extract_title(cr_run: CRRun) -> str:
    """Extract title from raw_cr_json."""
    if cr_run.raw_cr_json and isinstance(cr_run.raw_cr_json, dict):
        return cr_run.raw_cr_json.get("title", "")
    return ""


@router.get("/pipeline/list")
async def list_pipelines(request: Request) -> list[dict]:
    """List all pipeline runs, ordered by creation time (newest first)."""
    async with request.app.state.session_factory() as session:
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
async def get_pipeline_status(cr_id: str, request: Request) -> dict:
    """Get the current status of a pipeline run."""
    async with request.app.state.session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = result.scalar_one_or_none()
        if not cr_run:
            raise HTTPException(status_code=404, detail="CR not found")
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
        }


class InterventionRequest(BaseModel):
    instructions: str


@router.post("/pipeline/{cr_id}/intervene")
async def set_intervention(cr_id: str, body: InterventionRequest, request: Request) -> dict:
    """Set a human intervention for a running pipeline."""
    # Verify CR exists
    async with request.app.state.session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="CR not found")

    await request.app.state.intervention_mgr.set_intervention(cr_id, body.instructions)
    return {"status": "intervention_set", "cr_id": cr_id}


class ResumeRequest(BaseModel):
    state_overrides: dict[str, object] = {}


@router.post("/pipeline/{cr_id}/resume")
async def resume_pipeline(cr_id: str, body: ResumeRequest, request: Request) -> dict:
    """Resume a paused or failed pipeline, optionally overriding state."""
    async with request.app.state.session_factory() as session:
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
    redis = request.app.state.redis
    if body.state_overrides:
        override_key = f"hadron:cr:{cr_id}:resume_overrides"
        await redis.set(override_key, json.dumps(body.state_overrides), ex=3600)

    # Update DB status to running
    async with request.app.state.session_factory() as session:
        await session.execute(
            update(CRRun).where(CRRun.cr_id == cr_id).values(status="running", error=None)
        )
        await session.commit()

    # Spawn a new worker
    await request.app.state.job_spawner.spawn(cr_id)

    # Emit event so dashboard updates
    await request.app.state.event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.PIPELINE_STARTED,
        stage="controller",
        data={"resumed": True, "overrides": body.state_overrides},
    ))

    return {"status": "resumed", "cr_id": cr_id, "overrides": body.state_overrides}


class NudgeRequest(BaseModel):
    role: str
    message: str


@router.post("/pipeline/{cr_id}/nudge")
async def send_nudge(cr_id: str, body: NudgeRequest, request: Request) -> dict:
    """Send a nudge to a specific agent role in a running pipeline."""
    async with request.app.state.session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="CR not found")

    await request.app.state.intervention_mgr.set_nudge(cr_id, body.role, body.message)
    return {"status": "nudge_set", "cr_id": cr_id, "role": body.role}


@router.get("/pipeline/{cr_id}/conversation")
async def get_conversation(cr_id: str, key: str, request: Request) -> list:
    """Retrieve a stored agent conversation from Redis."""
    if not key.startswith(f"hadron:cr:{cr_id}:conv:"):
        raise HTTPException(status_code=400, detail="Invalid conversation key")

    redis: object = request.app.state.redis
    data = await redis.get(key)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversation not found or expired")

    raw = data.decode() if isinstance(data, bytes) else data
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse conversation data")


@router.get("/pipeline/{cr_id}/logs")
async def get_worker_logs(cr_id: str, request: Request) -> PlainTextResponse:
    """Retrieve worker logs for a CR."""
    redis: object = request.app.state.redis
    key = f"hadron:cr:{cr_id}:worker_log"
    data = await redis.get(key)
    if data is None:
        return PlainTextResponse("No logs available for this CR.", status_code=200)

    text = data.decode(errors="replace") if isinstance(data, bytes) else data
    return PlainTextResponse(text)
