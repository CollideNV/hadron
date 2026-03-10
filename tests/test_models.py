"""Tests for hadron.db.models ORM models (RepoRun + CRRun).

Requires aiosqlite:  pip install aiosqlite
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from hadron.db.models import Base, CRRun, RepoRun


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ── RepoRun ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repo_run_create_required_fields(session):
    rr = RepoRun(cr_id="CR-1", repo_url="https://github.com/o/r", repo_name="r")
    session.add(rr)
    await session.commit()

    assert rr.id is not None
    assert rr.cr_id == "CR-1"
    assert rr.repo_url == "https://github.com/o/r"
    assert rr.repo_name == "r"


@pytest.mark.asyncio
async def test_repo_run_defaults(session):
    rr = RepoRun(cr_id="CR-2", repo_url="https://github.com/o/r", repo_name="r")
    session.add(rr)
    await session.commit()

    assert rr.status == "pending"
    assert rr.cost_usd == 0.0


@pytest.mark.asyncio
async def test_repo_run_optional_fields_none(session):
    rr = RepoRun(cr_id="CR-3", repo_url="https://github.com/o/r", repo_name="r")
    session.add(rr)
    await session.commit()

    assert rr.branch_name is None
    assert rr.pr_url is None
    assert rr.pr_description is None
    assert rr.error is None


@pytest.mark.asyncio
async def test_repo_run_optional_fields_set(session):
    rr = RepoRun(
        cr_id="CR-4",
        repo_url="https://github.com/o/r",
        repo_name="r",
        branch_name="hadron/CR-4",
        pr_url="https://github.com/o/r/pull/42",
        pr_description="Adds the widget",
        error="something went wrong",
    )
    session.add(rr)
    await session.commit()

    assert rr.branch_name == "hadron/CR-4"
    assert rr.pr_url == "https://github.com/o/r/pull/42"
    assert rr.pr_description == "Adds the widget"
    assert rr.error == "something went wrong"


@pytest.mark.asyncio
async def test_multiple_repo_runs_share_cr_id(session):
    rr1 = RepoRun(cr_id="CR-5", repo_url="https://github.com/o/a", repo_name="a")
    rr2 = RepoRun(cr_id="CR-5", repo_url="https://github.com/o/b", repo_name="b")
    session.add_all([rr1, rr2])
    await session.commit()

    assert rr1.id != rr2.id
    assert rr1.cr_id == rr2.cr_id == "CR-5"


# ── CRRun ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_run_create_and_defaults(session):
    cr = CRRun(cr_id="CR-100")
    session.add(cr)
    await session.commit()

    assert cr.cr_id == "CR-100"
    assert cr.status == "pending"
    assert cr.source == "api"
    assert cr.cost_usd == 0.0
    assert cr.error is None
    assert cr.external_id is None
    assert cr.raw_cr_json is None
    assert cr.config_snapshot_json is None
