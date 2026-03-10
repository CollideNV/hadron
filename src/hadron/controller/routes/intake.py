"""Intake route — accepts CRs and spawns workers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from hadron.config.defaults import get_config_snapshot
from hadron.controller.job_spawner import SubprocessJobSpawner
from hadron.db.models import CRRun
from hadron.models.cr import RawChangeRequest

router = APIRouter(tags=["intake"])


@router.post("/pipeline/trigger")
async def trigger_pipeline(cr: RawChangeRequest, request: Request) -> dict:
    """Accept a change request and spawn a worker to process it."""
    session_factory = request.app.state.session_factory

    # Check for duplicate external_id
    if cr.external_id:
        from sqlalchemy import select
        async with session_factory() as session:
            existing = await session.execute(
                select(CRRun).where(CRRun.external_id == cr.external_id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail=f"CR with external_id '{cr.external_id}' already exists",
                )

    cr_id = f"CR-{uuid.uuid4().hex[:8]}"
    config_snapshot = get_config_snapshot()

    # Create CR run record
    cr_run = CRRun(
        cr_id=cr_id,
        status="pending",
        external_id=cr.external_id,
        source=cr.source,
        raw_cr_json=cr.model_dump(),
        config_snapshot_json=config_snapshot,
    )

    async with session_factory() as session:
        session.add(cr_run)
        await session.commit()

    # Spawn one worker per repo URL
    spawner = getattr(request.app.state, "job_spawner", None) or SubprocessJobSpawner(
        redis=getattr(request.app.state, "redis", None),
    )
    repo_urls = cr.repo_urls
    default_branch = cr.repo_default_branch

    workers_spawned: list[dict] = []
    for url in repo_urls:
        repo_name = url.rstrip("/").split("/")[-1]
        await spawner.spawn(cr_id, repo_url=url, repo_name=repo_name, default_branch=default_branch)
        workers_spawned.append({"repo_url": url, "repo_name": repo_name})

    return {"cr_id": cr_id, "status": "pending", "workers": workers_spawned}
