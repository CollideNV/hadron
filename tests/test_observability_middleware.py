"""Tests for the RequestIdMiddleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hadron.observability.logging import configure_logging
from hadron.observability.middleware import RequestIdMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"healthy": True}

    return app


class TestRequestIdMiddleware:
    """RequestIdMiddleware injects and returns X-Request-ID."""

    def setup_method(self) -> None:
        configure_logging(level="DEBUG", log_format="text")
        self.client = TestClient(_make_app())

    def test_generates_request_id(self) -> None:
        resp = self.client.get("/ping")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) == 16

    def test_preserves_incoming_request_id(self) -> None:
        resp = self.client.get("/ping", headers={"X-Request-ID": "custom-id-123"})
        assert resp.headers["X-Request-ID"] == "custom-id-123"

    def test_health_endpoint_still_works(self) -> None:
        resp = self.client.get("/healthz")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
