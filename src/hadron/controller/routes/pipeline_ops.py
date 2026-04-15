"""Pipeline mutation/orchestration routes (Orchestrator)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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


class CIResultRequest(BaseModel):
    repo_name: str
    passed: bool
    build_url: str = ""
    log_tail: str = ""  # last N chars of CI output


@router.post("/pipeline/{cr_id}/ci-result")
async def receive_ci_result(
    cr_id: str,
    body: CIResultRequest,
    session_factory: Any = Depends(get_session_factory),
    redis: Any = Depends(get_redis),
    spawner: Any = Depends(get_job_spawner),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict:
    """Receive CI results for a repo in a push_and_wait pipeline.

    When CI passes, the pipeline resumes to delivery. When CI fails,
    the pipeline resumes to implementation with CI failure context so
    the agent can fix the issues.
    """
    # Validate CR exists and the repo is waiting for CI
    async with session_factory() as session:
        result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = result.scalar_one_or_none()
        if not cr_run:
            raise HTTPException(status_code=404, detail="CR not found")

    async with session_factory() as session:
        result = await session.execute(
            select(RepoRun).where(
                RepoRun.cr_id == cr_id,
                RepoRun.repo_name == body.repo_name,
            )
        )
        repo_run = result.scalar_one_or_none()
        if not repo_run:
            raise HTTPException(status_code=404, detail=f"Repo '{body.repo_name}' not found for CR")

    # Emit CI result event
    await event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.STAGE_COMPLETED,
        stage="ci",
        data={
            "repo": body.repo_name,
            "passed": body.passed,
            "build_url": body.build_url,
        },
    ))

    if body.passed:
        # CI passed — resume with clean state, will proceed through review → rebase → delivery
        overrides: dict[str, object] = {}
    else:
        # CI failed — resume from implementation with CI failure context
        overrides = {
            "ci_failure_log": body.log_tail[-4000:] if body.log_tail else "",
            "ci_build_url": body.build_url,
        }

    # Store overrides and respawn worker
    override_key = f"hadron:cr:{cr_id}:resume_overrides"
    await redis.set(override_key, json.dumps(overrides), ex=3600)

    async with session_factory() as session:
        await session.execute(
            update(CRRun).where(CRRun.cr_id == cr_id).values(status="running", error=None)
        )
        await session.execute(
            update(RepoRun)
            .where(RepoRun.cr_id == cr_id, RepoRun.repo_name == body.repo_name)
            .values(status="running", error=None)
        )
        await session.commit()

    await spawner.spawn(
        cr_id, repo_url=repo_run.repo_url, repo_name=repo_run.repo_name,
    )

    await event_bus.emit(PipelineEvent(
        cr_id=cr_id,
        event_type=EventType.PIPELINE_RESUMED,
        stage="controller",
        data={"trigger": "ci_result", "repo": body.repo_name, "ci_passed": body.passed},
    ))

    return {
        "status": "resumed" if body.passed else "resumed_for_fix",
        "cr_id": cr_id,
        "repo_name": body.repo_name,
        "ci_passed": body.passed,
    }


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
