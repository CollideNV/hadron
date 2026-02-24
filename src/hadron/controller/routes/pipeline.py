"""Pipeline status and intervention routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from hadron.db.models import CRRun

router = APIRouter(tags=["pipeline"])


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
