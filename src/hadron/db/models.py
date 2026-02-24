"""ORM models for Hadron's own tables (not LangGraph checkpoint tables)."""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, Float, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CRRun(Base):
    """Tracks a single Change Request pipeline run."""

    __tablename__ = "cr_runs"

    cr_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )  # pending | running | paused | completed | failed
    external_id: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="api")
    raw_cr_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Immutable audit trail for all significant actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cr_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
