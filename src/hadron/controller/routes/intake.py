"""Intake route — accepts CRs and spawns workers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.config.defaults import BRANCH_PREFIX, get_config_snapshot
from hadron.controller.dependencies import get_job_spawner, get_session_factory
from hadron.controller.job_spawner import JobSpawner
from hadron.db.models import CRRun, PipelineSetting, PromptTemplate, RepoRun
from hadron.git.url import extract_repo_name
from hadron.models.cr import RawChangeRequest

router = APIRouter(tags=["intake"])


@router.post("/pipeline/trigger")
async def trigger_pipeline(
    cr: RawChangeRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
    spawner: JobSpawner = Depends(get_job_spawner),
) -> dict:
    """Accept a change request and spawn one worker per repo."""
    # Check for duplicate external_id
    if cr.external_id:
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

    # Freeze prompt templates and backend template into config snapshot
    async with session_factory() as session:
        result = await session.execute(select(PromptTemplate))
        prompts = {row.role: row.content for row in result.scalars()}
        if prompts:
            config_snapshot["prompts"] = prompts

        # Resolve template slug: request → DB default → "anthropic"
        template_slug = cr.template_slug
        if not template_slug:
            result = await session.execute(
                select(PipelineSetting).where(PipelineSetting.key == "default_template")
            )
            row = result.scalar_one_or_none()
            if row and isinstance(row.value_json, dict):
                template_slug = row.value_json.get("slug", "anthropic")
            elif row and isinstance(row.value_json, str):
                template_slug = row.value_json
            else:
                template_slug = "anthropic"

        # Load template data from DB (or use built-in defaults via settings helper)
        result = await session.execute(
            select(PipelineSetting).where(PipelineSetting.key == "backend_templates")
        )
        row = result.scalar_one_or_none()
        template_data: dict | None = None
        if row and isinstance(row.value_json, list):
            for t in row.value_json:
                if t.get("slug") == template_slug:
                    template_data = t
                    break

        # Freeze template into config snapshot
        config_snapshot["pipeline"]["template_slug"] = template_slug
        if template_data:
            config_snapshot["pipeline"]["template"] = template_data

    default_branch = cr.repo_default_branch

    # Create CR run + RepoRun records in a single transaction
    cr_run = CRRun(
        cr_id=cr_id,
        status="pending",
        external_id=cr.external_id,
        source=cr.source,
        raw_cr_json=cr.model_dump(),
        config_snapshot_json=config_snapshot,
    )

    repo_runs: list[RepoRun] = []
    for url in cr.repo_urls:
        repo_name = extract_repo_name(url)
        repo_runs.append(RepoRun(
            cr_id=cr_id,
            repo_url=url,
            repo_name=repo_name,
            status="pending",
            branch_name=f"{BRANCH_PREFIX}{cr_id}",
        ))

    async with session_factory() as session:
        session.add(cr_run)
        for rr in repo_runs:
            session.add(rr)
        await session.commit()

    # Spawn one worker per repo URL
    workers_spawned: list[dict] = []
    for url in cr.repo_urls:
        repo_name = extract_repo_name(url)
        await spawner.spawn(cr_id, repo_url=url, repo_name=repo_name, default_branch=default_branch)
        workers_spawned.append({"repo_url": url, "repo_name": repo_name})

    return {"cr_id": cr_id, "status": "pending", "workers": workers_spawned}
