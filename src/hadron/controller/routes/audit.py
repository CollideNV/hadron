"""Audit log routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.controller.dependencies import get_session_factory
from hadron.db.models import AuditLog

router = APIRouter(tags=["audit"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    id: int
    cr_id: str | None
    action: str
    details: dict | None
    timestamp: str


class AuditLogPage(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/audit-log")
async def get_audit_log(
    page: int = 1,
    page_size: int = 50,
    action: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AuditLogPage:
    """Return paginated audit log entries, optionally filtered by action."""
    async with session_factory() as session:
        base = select(AuditLog)
        count_base = select(func.count(AuditLog.id))

        if action:
            base = base.where(AuditLog.action == action)
            count_base = count_base.where(AuditLog.action == action)

        # Total count
        total_result = await session.execute(count_base)
        total = total_result.scalar_one()

        # Paginated results
        result = await session.execute(
            base.order_by(AuditLog.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = result.scalars().all()

        items = [
            AuditLogEntry(
                id=row.id,
                cr_id=row.cr_id,
                action=row.action,
                details=row.details,
                timestamp=row.timestamp.isoformat() if row.timestamp else "",
            )
            for row in rows
        ]

    return AuditLogPage(items=items, total=total, page=page, page_size=page_size)
