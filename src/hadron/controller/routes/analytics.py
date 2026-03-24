"""Analytics routes — aggregate pipeline metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.controller.dependencies import get_session_factory
from hadron.db.models import CRRun, RepoRun

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary")
async def analytics_summary(
    days: int = 30,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """Aggregate pipeline analytics across all CRs within the given time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with session_factory() as session:
        # Single aggregation query grouped by status
        result = await session.execute(
            select(
                CRRun.status,
                func.count().label("cnt"),
                func.coalesce(func.sum(CRRun.cost_usd), 0).label("cost"),
            )
            .where(CRRun.created_at >= cutoff)
            .group_by(CRRun.status)
        )
        rows = result.all()

    status_counts: dict[str, int] = {}
    total_cost = 0.0
    total_runs = 0
    for row in rows:
        status_counts[row.status] = row.cnt
        total_runs += row.cnt
        total_cost += float(row.cost)

    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)

    return {
        "total_runs": total_runs,
        "status_counts": status_counts,
        "success_rate": completed / (completed + failed) if (completed + failed) > 0 else 0,
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(total_cost / total_runs, 4) if total_runs > 0 else 0,
        "stage_durations": [],  # TODO: derive from events
        "daily_stats": [],  # TODO: derive from timestamps
    }


@router.get("/analytics/cost")
async def analytics_cost(
    group_by: str = "stage",
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """Aggregate cost data across completed CRs."""
    async with session_factory() as session:
        if group_by == "repo":
            result = await session.execute(
                select(
                    RepoRun.repo_name,
                    func.coalesce(func.sum(RepoRun.cost_usd), 0).label("cost_usd"),
                    func.count().label("runs"),
                ).group_by(RepoRun.repo_name)
            )
            groups = [
                {"key": row.repo_name, "label": row.repo_name, "cost_usd": round(float(row.cost_usd), 4), "runs": row.runs, "tokens": 0}
                for row in result
            ]
        else:
            # For stage/model grouping, would need event data — stub for now
            groups = []

    total_cost = sum(g["cost_usd"] for g in groups)
    return {
        "group_by": group_by,
        "total_cost_usd": round(total_cost, 4),
        "groups": groups,
    }
