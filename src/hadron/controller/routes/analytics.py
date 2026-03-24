"""Analytics routes — aggregate pipeline metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hadron.controller.dependencies import get_db
from hadron.db.models import CRRun, RepoRun

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate pipeline analytics across all CRs."""
    result = await db.execute(select(CRRun))
    runs = result.scalars().all()

    status_counts: dict[str, int] = {}
    total_cost = 0.0
    for r in runs:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        total_cost += r.cost_usd or 0.0

    total = len(runs)
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)

    return {
        "total_runs": total,
        "status_counts": status_counts,
        "success_rate": completed / (completed + failed) if (completed + failed) > 0 else 0,
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(total_cost / total, 4) if total > 0 else 0,
        "stage_durations": [],  # TODO: derive from events
        "daily_stats": [],  # TODO: derive from timestamps
    }


@router.get("/cost")
async def analytics_cost(
    group_by: str = "stage",
    db: AsyncSession = Depends(get_db),
):
    """Aggregate cost data across completed CRs."""
    if group_by == "repo":
        result = await db.execute(
            select(
                RepoRun.repo_name,
                func.sum(RepoRun.cost_usd).label("cost_usd"),
                func.count().label("runs"),
            ).group_by(RepoRun.repo_name)
        )
        groups = [
            {"key": row.repo_name, "label": row.repo_name, "cost_usd": round(row.cost_usd or 0, 4), "runs": row.runs, "tokens": 0}
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
