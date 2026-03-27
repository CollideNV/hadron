"""Analytics routes — aggregate pipeline metrics."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import cast, func, select, Date
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.controller.dependencies import get_session_factory
from hadron.db.models import CRRun, RepoRun, RunSummary

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
    stage_durations: list[dict[str, object]]
    daily_stats: list[dict[str, object]]


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
# Helpers
# ---------------------------------------------------------------------------


def _compute_stage_durations(
    summaries: list[RunSummary],
) -> list[dict[str, object]]:
    """Compute avg and p95 stage durations from RunSummary records."""
    stage_durations: dict[str, list[float]] = defaultdict(list)

    for s in summaries:
        timings = s.stage_timings or {}
        for key, info in timings.items():
            dur = info.get("duration_s")
            stage_name = info.get("stage", key)
            if dur is not None:
                stage_durations[stage_name].append(dur)

    result = []
    for stage_name, durations in sorted(stage_durations.items()):
        if not durations:
            continue
        durations_sorted = sorted(durations)
        p95_idx = max(0, int(len(durations_sorted) * 0.95) - 1)
        result.append({
            "stage": stage_name,
            "avg_seconds": round(statistics.mean(durations), 2),
            "p95_seconds": round(durations_sorted[p95_idx], 2),
            "sample_count": len(durations),
        })
    return result


def _compute_daily_stats(
    summaries: list[RunSummary],
) -> list[dict[str, object]]:
    """Compute per-day stats from RunSummary records."""
    days: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "completed": 0, "failed": 0, "paused": 0, "cost_usd": 0.0}
    )

    for s in summaries:
        day_key = (
            s.started_at.strftime("%Y-%m-%d")
            if s.started_at
            else s.created_at.strftime("%Y-%m-%d")
        )
        entry = days[day_key]
        entry["total"] += 1
        entry["cost_usd"] += s.total_cost_usd or 0.0
        status = s.final_status
        if status in ("completed", "failed", "paused"):
            entry[status] += 1

    return [
        {"date": day, **stats}
        for day, stats in sorted(days.items())
    ]


def _aggregate_cost_by_stage(
    summaries: list[RunSummary],
) -> list[CostGroupResponse]:
    """Aggregate cost by stage from stage_timings JSON."""
    stage_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cost_usd": 0.0, "runs": 0, "tokens": 0}
    )

    for s in summaries:
        timings = s.stage_timings or {}
        for key, info in timings.items():
            stage_name = info.get("stage", key)
            entry = stage_data[stage_name]
            entry["runs"] += 1

    # stage_timings doesn't track per-stage cost yet, so distribute proportionally
    # by duration as a reasonable approximation
    for s in summaries:
        timings = s.stage_timings or {}
        total_dur = sum(
            (info.get("duration_s") or 0) for info in timings.values()
        )
        if total_dur <= 0:
            continue
        for key, info in timings.items():
            stage_name = info.get("stage", key)
            dur = info.get("duration_s") or 0
            fraction = dur / total_dur
            stage_data[stage_name]["cost_usd"] += (s.total_cost_usd or 0) * fraction

    return [
        CostGroupResponse(
            key=stage, label=stage,
            cost_usd=round(data["cost_usd"], 4),
            runs=data["runs"], tokens=data["tokens"],
        )
        for stage, data in sorted(stage_data.items())
    ]


def _aggregate_cost_by_model(
    summaries: list[RunSummary],
) -> list[CostGroupResponse]:
    """Aggregate cost by model from model_breakdown JSON."""
    model_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cost_usd": 0.0, "runs": 0, "tokens": 0}
    )

    for s in summaries:
        breakdown = s.model_breakdown or {}
        for model_name, info in breakdown.items():
            entry = model_data[model_name]
            entry["cost_usd"] += info.get("cost_usd", 0.0)
            entry["runs"] += info.get("api_calls", 0)
            entry["tokens"] += info.get("input_tokens", 0) + info.get("output_tokens", 0)

    return [
        CostGroupResponse(
            key=model, label=model,
            cost_usd=round(data["cost_usd"], 4),
            runs=data["runs"], tokens=data["tokens"],
        )
        for model, data in sorted(model_data.items())
    ]


def _aggregate_cost_by_day(
    summaries: list[RunSummary],
) -> list[CostGroupResponse]:
    """Aggregate cost by day."""
    day_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cost_usd": 0.0, "runs": 0, "tokens": 0}
    )

    for s in summaries:
        day_key = (
            s.started_at.strftime("%Y-%m-%d")
            if s.started_at
            else s.created_at.strftime("%Y-%m-%d")
        )
        entry = day_data[day_key]
        entry["cost_usd"] += s.total_cost_usd or 0.0
        entry["runs"] += 1
        entry["tokens"] += (s.total_input_tokens or 0) + (s.total_output_tokens or 0)

    return [
        CostGroupResponse(
            key=day, label=day,
            cost_usd=round(data["cost_usd"], 4),
            runs=data["runs"], tokens=data["tokens"],
        )
        for day, data in sorted(day_data.items())
    ]


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
                func.coalesce(func.sum(CRRun.cost_usd), 0).label("cost"),
            )
            .where(CRRun.created_at >= cutoff)
            .group_by(CRRun.status)
        )
        rows = result.all()

        # Load RunSummary records for stage durations and daily stats
        summary_result = await session.execute(
            select(RunSummary).where(RunSummary.created_at >= cutoff)
        )
        summaries = list(summary_result.scalars().all())

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
        stage_durations=_compute_stage_durations(summaries),
        daily_stats=_compute_daily_stats(summaries),
    )


@router.get("/analytics/cost")
async def analytics_cost(
    group_by: Literal["stage", "model", "repo", "day"] = "stage",
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AnalyticsCostResponse:
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
            # Load RunSummary for stage/model/day grouping
            summary_result = await session.execute(select(RunSummary))
            summaries = list(summary_result.scalars().all())

            if group_by == "stage":
                groups = _aggregate_cost_by_stage(summaries)
            elif group_by == "model":
                groups = _aggregate_cost_by_model(summaries)
            else:  # day
                groups = _aggregate_cost_by_day(summaries)

    total_cost = sum(g.cost_usd for g in groups)
    return AnalyticsCostResponse(
        group_by=group_by,
        total_cost_usd=round(total_cost, 4),
        groups=groups,
    )
