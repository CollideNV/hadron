"""Release mutation/orchestration routes (Orchestrator).

The Controller tracks all repo workers for a CR. When all workers have
completed (pushed PRs), the human can review and approve the release,
which triggers merging of all PRs.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from hadron.controller.dependencies import get_event_bus, get_session_factory
from hadron.db.models import CRRun, RepoRun
from hadron.events.bus import EventBus
from hadron.git.github import (
    GitHubAPIError,
    is_pr_approved,
    merge_pull_request,
    pr_number_from_url,
)
from hadron.git.url import extract_owner_repo
from hadron.models.events import EventType, PipelineEvent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["release"])


@router.post("/pipeline/{cr_id}/release/approve")
async def approve_release(
    cr_id: str,
    session_factory: Any = Depends(get_session_factory),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict:
    """Approve the release gate — verify PR approvals and merge all PRs."""
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

    # Check PR approvals (all-or-nothing)
    repos_to_merge: list[tuple[RepoRun, str, str, int]] = []  # (rr, owner, repo, pr_number)
    skipped: list[str] = []
    for rr in repo_runs:
        if not rr.pr_url:
            skipped.append(rr.repo_name)
            logger.warning("No PR URL for repo %s — skipping merge", rr.repo_name)
            continue
        try:
            owner, repo_short = extract_owner_repo(rr.repo_url)
            pr_number = pr_number_from_url(rr.pr_url)
        except (ValueError, IndexError) as e:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot parse PR info for {rr.repo_name}: {e}",
            )
        repos_to_merge.append((rr, owner, repo_short, pr_number))

    # Verify all PRs are approved before merging any
    unapproved: list[str] = []
    for rr, owner, repo_short, pr_number in repos_to_merge:
        try:
            approved = await is_pr_approved(owner, repo_short, pr_number)
        except GitHubAPIError as e:
            raise HTTPException(status_code=502, detail=f"GitHub API error for {rr.repo_name}: {e}")
        if not approved:
            unapproved.append(f"{rr.repo_name} (PR #{pr_number})")

    if unapproved:
        raise HTTPException(
            status_code=409,
            detail=f"PRs not yet approved: {', '.join(unapproved)}. Approve them on GitHub first.",
        )

    # Merge all approved PRs
    merge_errors: list[str] = []
    merged: list[str] = []
    for rr, owner, repo_short, pr_number in repos_to_merge:
        try:
            await merge_pull_request(owner, repo_short, pr_number)
            merged.append(rr.repo_name)
        except GitHubAPIError as e:
            merge_errors.append(f"{rr.repo_name} (PR #{pr_number}): {e}")

    if merge_errors:
        raise HTTPException(
            status_code=409,
            detail=f"Merge failed for: {'; '.join(merge_errors)}",
        )

    # Update CR status to completed
    async with session_factory() as session:
        await session.execute(
            update(CRRun)
            .where(CRRun.cr_id == cr_id)
            .values(status="completed")
        )
        await session.commit()

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
        "repos_merged": merged,
        "repos_skipped": skipped,
    }
