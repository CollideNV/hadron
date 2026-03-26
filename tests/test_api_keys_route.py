"""Tests for API key management routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hadron.controller.routes.settings import router
from hadron.security.crypto import encrypt_value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(session_factory) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.session_factory = session_factory
    return app


def _build_factory(scalar_one=None):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_one

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory, mock_session


@pytest.fixture()
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("HADRON_ENCRYPTION_KEY", key)
    return key


# ---------------------------------------------------------------------------
# GET /settings/api-keys
# ---------------------------------------------------------------------------


class TestGetApiKeys:
    async def test_no_keys_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear all relevant env vars
        for var in (
            "HADRON_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY",
            "HADRON_OPENAI_API_KEY", "OPENAI_API_KEY",
            "HADRON_GEMINI_API_KEY", "GEMINI_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)

        factory, _ = _build_factory(scalar_one=None)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/settings/api-keys")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        for item in data:
            assert item["is_configured"] is False
            assert item["source"] == "none"
            assert item["masked_value"] == ""

    async def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HADRON_ANTHROPIC_API_KEY", "sk-ant-test1234abcd")
        monkeypatch.delenv("HADRON_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("HADRON_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        factory, _ = _build_factory(scalar_one=None)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/settings/api-keys")

        data = resp.json()
        anthropic = next(k for k in data if k["key_name"] == "anthropic_api_key")
        assert anthropic["is_configured"] is True
        assert anthropic["source"] == "environment"
        assert anthropic["masked_value"] == "••••abcd"
        # Full key must never appear
        assert "sk-ant-test1234abcd" not in str(data)

    async def test_db_key_shown(
        self, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HADRON_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("HADRON_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("HADRON_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        ciphertext = encrypt_value("sk-secret-key-wxyz")
        setting = SimpleNamespace(
            key="api_keys",
            value_json={"anthropic_api_key": ciphertext},
        )
        factory, _ = _build_factory(scalar_one=setting)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/settings/api-keys")

        data = resp.json()
        anthropic = next(k for k in data if k["key_name"] == "anthropic_api_key")
        assert anthropic["is_configured"] is True
        assert anthropic["source"] == "database"
        assert anthropic["masked_value"] == "••••wxyz"
        assert "sk-secret-key-wxyz" not in str(data)


# ---------------------------------------------------------------------------
# PUT /settings/api-keys
# ---------------------------------------------------------------------------


class TestSetApiKey:
    async def test_set_key_success(self, encryption_key: str) -> None:
        factory, mock_session = _build_factory(scalar_one=None)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.put(
                "/api/settings/api-keys",
                json={"key_name": "anthropic_api_key", "value": "sk-ant-new-key-5678"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["key_name"] == "anthropic_api_key"
        assert data["is_configured"] is True
        assert data["source"] == "database"
        assert data["masked_value"] == "••••5678"
        assert "sk-ant-new-key-5678" not in str(data)

        # Verify audit log was written (session.add called with AuditLog)
        add_calls = mock_session.add.call_args_list
        audit_args = [c for c in add_calls if hasattr(c[0][0], "action")]
        assert len(audit_args) == 1
        audit = audit_args[0][0][0]
        assert audit.action == "api_key_updated"
        assert audit.details == {"key_name": "anthropic_api_key"}

    async def test_set_unknown_key(self, encryption_key: str) -> None:
        factory, _ = _build_factory()
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.put(
                "/api/settings/api-keys",
                json={"key_name": "unknown_key", "value": "secret"},
            )

        assert resp.status_code == 422

    async def test_set_empty_value(self, encryption_key: str) -> None:
        factory, _ = _build_factory()
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.put(
                "/api/settings/api-keys",
                json={"key_name": "anthropic_api_key", "value": "  "},
            )

        assert resp.status_code == 422

    async def test_set_without_encryption_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HADRON_ENCRYPTION_KEY", raising=False)
        factory, _ = _build_factory()
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.put(
                "/api/settings/api-keys",
                json={"key_name": "anthropic_api_key", "value": "sk-key"},
            )

        assert resp.status_code == 503
        assert "HADRON_ENCRYPTION_KEY" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /settings/api-keys/{key_name}
# ---------------------------------------------------------------------------


class TestClearApiKey:
    async def test_clear_key(
        self, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HADRON_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        ciphertext = encrypt_value("sk-old-key-1234")
        setting = SimpleNamespace(
            key="api_keys",
            value_json={"anthropic_api_key": ciphertext},
        )
        factory, mock_session = _build_factory(scalar_one=setting)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete("/api/settings/api-keys/anthropic_api_key")

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_configured"] is False
        assert data["source"] == "none"

    async def test_clear_falls_back_to_env(
        self, encryption_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HADRON_ANTHROPIC_API_KEY", "sk-env-fallback-9xyz")

        setting = SimpleNamespace(
            key="api_keys",
            value_json={"anthropic_api_key": encrypt_value("sk-db-key")},
        )
        factory, _ = _build_factory(scalar_one=setting)
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete("/api/settings/api-keys/anthropic_api_key")

        data = resp.json()
        assert data["is_configured"] is True
        assert data["source"] == "environment"
        assert data["masked_value"] == "••••9xyz"

    async def test_clear_unknown_key(self, encryption_key: str) -> None:
        factory, _ = _build_factory()
        app = _make_app(factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete("/api/settings/api-keys/bogus_key")

        assert resp.status_code == 422
