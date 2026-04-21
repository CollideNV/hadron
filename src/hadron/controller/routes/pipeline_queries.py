"""Pipeline read-only query routes (Dashboard API)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select

from hadron.controller.dependencies import get_redis, get_session_factory
from hadron.db.models import CRRun, RepoRun, RunSummary

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline"])


def _extract_title(cr_run: CRRun) -> str:
    """Extract title from raw_cr_json."""
    if cr_run.raw_cr_json and isinstance(cr_run.raw_cr_json, dict):
        return cr_run.raw_cr_json.get("title", "")
    return ""


@router.get("/pipeline/list")
async def list_pipelines(
    search: str | None = None,
    status: str | None = None,
    sort: str = "newest",
    session_factory: Any = Depends(get_session_factory),
) -> list[dict]:
    """List pipeline runs with optional search, status filter, and sort."""
    query = select(CRRun)

    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            query = query.where(CRRun.status.in_(statuses))

    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                CRRun.cr_id.ilike(pattern),
                CRRun.raw_cr_json["title"].astext.ilike(pattern),
            )
        )

    if sort == "oldest":
        query = query.order_by(CRRun.created_at.asc())
    elif sort == "cost":
        query = query.order_by(CRRun.cost_usd.desc())
    else:
        query = query.order_by(CRRun.created_at.desc())

    query = query.limit(100)

    async with session_factory() as session:
        result = await session.execute(query)
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
            "pause_reason": cr_run.pause_reason,
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


@router.get("/pipeline/{cr_id}/retrospective")
async def get_retrospective(
    cr_id: str,
    session_factory: Any = Depends(get_session_factory),
) -> list[dict]:
    """Return retrospective insights for a pipeline run."""
    async with session_factory() as session:
        result = await session.execute(
            select(RunSummary).where(RunSummary.cr_id == cr_id)
        )
        summaries = result.scalars().all()

    if not summaries:
        raise HTTPException(status_code=404, detail="No run summary found for this CR")

    return [
        {
            "repo_name": s.repo_name,
            "final_status": s.final_status,
            "duration_seconds": s.duration_seconds,
            "total_cost_usd": s.total_cost_usd,
            "insights": s.retrospective_json or [],
        }
        for s in summaries
    ]


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
