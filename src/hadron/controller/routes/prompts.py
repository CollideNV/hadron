"""Prompt template management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hadron.controller.dependencies import get_session_factory
from hadron.db.models import AuditLog, PromptTemplate

router = APIRouter(tags=["prompts"])


class PromptSummary(BaseModel):
    role: str
    description: str
    version: int
    updated_at: str | None


class PromptDetail(BaseModel):
    role: str
    content: str
    description: str
    version: int
    updated_at: str | None


class PromptUpdate(BaseModel):
    content: str


@router.get("/prompts")
async def list_prompts(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[PromptSummary]:
    """List all prompt templates (without content)."""
    async with session_factory() as session:
        result = await session.execute(
            select(PromptTemplate).order_by(PromptTemplate.role)
        )
        return [
            PromptSummary(
                role=row.role,
                description=row.description,
                version=row.version,
                updated_at=row.updated_at.isoformat() if row.updated_at else None,
            )
            for row in result.scalars()
        ]


@router.get("/prompts/{role}")
async def get_prompt(
    role: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> PromptDetail:
    """Get a single prompt template with full content."""
    async with session_factory() as session:
        result = await session.execute(
            select(PromptTemplate).where(PromptTemplate.role == role)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Prompt template '{role}' not found")
        return PromptDetail(
            role=row.role,
            content=row.content,
            description=row.description,
            version=row.version,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )


@router.put("/prompts/{role}")
async def update_prompt(
    role: str,
    body: PromptUpdate,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> PromptDetail:
    """Update a prompt template's content. Bumps version and writes AuditLog."""
    async with session_factory() as session:
        result = await session.execute(
            select(PromptTemplate).where(PromptTemplate.role == role)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Prompt template '{role}' not found")

        row.content = body.content
        row.version = row.version + 1

        session.add(AuditLog(
            action="prompt_template_updated",
            details={"role": role, "version": row.version},
        ))

        await session.commit()
        await session.refresh(row)

        return PromptDetail(
            role=row.role,
            content=row.content,
            description=row.description,
            version=row.version,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )
