"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import Response

from hadron.observability.metrics import generate_metrics, metrics_available

router = APIRouter(tags=["observability"])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    """Expose Prometheus metrics in text exposition format."""
    if not metrics_available():
        return Response(
            content="# prometheus-client not installed\n",
            media_type="text/plain",
            status_code=501,
        )
    return Response(
        content=generate_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
