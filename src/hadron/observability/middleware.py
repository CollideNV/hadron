"""FastAPI middleware for observability — request ID injection and HTTP metrics."""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from hadron.observability.logging import bind_contextvars, clear_contextvars

logger = structlog.stdlib.get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into every HTTP request's structlog context."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        clear_contextvars()
        bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id

        # Log the request (skip health/metrics noise)
        path = request.url.path
        if path not in ("/healthz", "/readyz", "/metrics"):
            logger.info(
                "http_request",
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=round(duration_ms, 1),
            )

        # Record Prometheus metrics if available
        try:
            from hadron.observability.metrics import (
                HTTP_REQUEST_DURATION,
                HTTP_REQUESTS_TOTAL,
            )

            method = request.method
            status = str(response.status_code)
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(
                duration_ms / 1000
            )
        except ImportError:
            pass  # prometheus-client not installed

        clear_contextvars()
        return response
