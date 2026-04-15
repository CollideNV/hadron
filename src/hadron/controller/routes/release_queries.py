"""Release read-only query routes (Dashboard API)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from hadron.controller.dependencies import get_session_factory
from hadron.db.models import CRRun, RepoRun

logger = logging.getLogger(__name__)
router = APIRouter(tags=["release"])


@router.get("/pipeline/{cr_id}/release")
async def get_release_status(
    cr_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> dict:
    """Get the release readiness status for a CR across all repos."""
    async with session_factory() as session:
        cr_result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = cr_result.scalar_one_or_none()
        if not cr_run:
            raise HTTPException(status_code=404, detail="CR not found")

        repo_result = await session.execute(
            select(RepoRun).where(RepoRun.cr_id == cr_id)
        )
        repo_runs = repo_result.scalars().all()

    repos = []
    all_completed = True
    any_failed = False
    for rr in repo_runs:
        repos.append({
            "repo_name": rr.repo_name,
            "repo_url": rr.repo_url,
            "status": rr.status,
            "branch_name": rr.branch_name,
            "pr_url": rr.pr_url,
            "cost_usd": rr.cost_usd,
            "error": rr.error,
        })
        if rr.status != "completed":
            all_completed = False
        if rr.status == "failed":
            any_failed = True

    return {
        "cr_id": cr_id,
        "cr_status": cr_run.status,
        "ready_for_release": all_completed and len(repos) > 0,
        "any_failed": any_failed,
        "repos": repos,
        "total_repos": len(repos),
        "completed_repos": sum(1 for r in repos if r["status"] == "completed"),
    }
