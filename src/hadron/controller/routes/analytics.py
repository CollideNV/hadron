"""Analytics routes — aggregate pipeline metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.controller.dependencies import get_session_factory
from hadron.db.models import CRRun, RepoRun

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AnalyticsSummaryResponse(BaseModel):
    total_runs: int
    status_counts: dict[str, int]
    success_rate: float
    total_cost_usd: float
    avg_cost_usd: float
    stage_durations: list
    daily_stats: list


class CostGroupResponse(BaseModel):
    key: str
    label: str
    cost_usd: float
    runs: int
    tokens: int


class AnalyticsCostResponse(BaseModel):
    group_by: str
    total_cost_usd: float
    groups: list[CostGroupResponse]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/analytics/summary")
async def analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AnalyticsSummaryResponse:
    """Aggregate pipeline analytics across all CRs within the given time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with session_factory() as session:
        result = await session.execute(
            select(
                CRRun.status,
                func.count().label("cnt"),
                # COALESCE ensures cost is never NULL — safe to use float() on result
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

    return AnalyticsSummaryResponse(
        total_runs=total_runs,
        status_counts=status_counts,
        success_rate=completed / (completed + failed) if (completed + failed) > 0 else 0,
        total_cost_usd=round(total_cost, 4),
        avg_cost_usd=round(total_cost / total_runs, 4) if total_runs > 0 else 0,
        stage_durations=[],  # TODO: derive from events
        daily_stats=[],  # TODO: derive from timestamps
    )


@router.get("/analytics/cost")
async def analytics_cost(
    group_by: str = "stage",
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AnalyticsCostResponse:
    """Aggregate cost data across completed CRs."""
    async with session_factory() as session:
        if group_by == "repo":
            result = await session.execute(
                select(
                    RepoRun.repo_name,
                    # COALESCE ensures cost_usd is never NULL
                    func.coalesce(func.sum(RepoRun.cost_usd), 0).label("cost_usd"),
                    func.count().label("runs"),
                ).group_by(RepoRun.repo_name)
            )
            rows = result.all()
            groups = [
                CostGroupResponse(
                    key=row.repo_name,
                    label=row.repo_name,
                    cost_usd=round(float(row.cost_usd), 4),
                    runs=row.runs,
                    tokens=0,
                )
                for row in rows
            ]
        else:
            # For stage/model grouping, would need event data — stub for now
            groups = []

    total_cost = sum(g.cost_usd for g in groups)
    return AnalyticsCostResponse(
        group_by=group_by,
        total_cost_usd=round(total_cost, 4),
        groups=groups,
    )
