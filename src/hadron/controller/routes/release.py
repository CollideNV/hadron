"""Release coordination routes — Controller-level release gate.

The Controller tracks all repo workers for a CR. When all workers have
completed (pushed PRs), the human can review and approve the release,
which triggers merging of all PRs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update

from hadron.db.models import CRRun, RepoRun
from hadron.models.events import EventType, PipelineEvent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["release"])


@router.get("/pipeline/{cr_id}/release")
async def get_release_status(cr_id: str, request: Request) -> dict:
    """Get the release readiness status for a CR across all repos."""
    session_factory = request.app.state.session_factory

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


@router.post("/pipeline/{cr_id}/release/approve")
async def approve_release(cr_id: str, request: Request) -> dict:
    """Approve the release gate — marks CR as released.

    In a full implementation this would trigger PR merging via the git
    provider API. For now it updates the CR status and emits events.
    """
    session_factory = request.app.state.session_factory
    event_bus = request.app.state.event_bus

    async with session_factory() as session:
        cr_result = await session.execute(select(CRRun).where(CRRun.cr_id == cr_id))
        cr_run = cr_result.scalar_one_or_none()
        if not cr_run:
            raise HTTPException(status_code=404, detail="CR not found")

        repo_result = await session.execute(
            select(RepoRun).where(RepoRun.cr_id == cr_id)
        )
        repo_runs = repo_result.scalars().all()

    if not repo_runs:
        raise HTTPException(status_code=409, detail="No repos found for this CR")

    # Verify all repos are completed
    not_ready = [rr for rr in repo_runs if rr.status != "completed"]
    if not_ready:
        names = [rr.repo_name for rr in not_ready]
        raise HTTPException(
            status_code=409,
            detail=f"Not all repos are ready: {', '.join(names)} ({[rr.status for rr in not_ready]})",
        )

    # TODO: Merge PRs via git provider API (GitHub, GitLab, etc.)
    # For each repo_run with a pr_url, call the merge API.

    # Update CR status to completed
    async with session_factory() as session:
        await session.execute(
            update(CRRun)
            .where(CRRun.cr_id == cr_id)
            .values(status="completed")
        )
        await session.commit()

    if event_bus:
        await event_bus.emit(PipelineEvent(
            cr_id=cr_id,
            event_type=EventType.PIPELINE_COMPLETED,
            stage="release_gate",
            data={
                "approved_by": "human",
                "repos": [rr.repo_name for rr in repo_runs],
            },
        ))

    return {
        "cr_id": cr_id,
        "status": "released",
        "repos_merged": [rr.repo_name for rr in repo_runs],
    }
