"""Reverse proxy for orchestrator and SSE gateway routes.

When running in K8s split mode, the Dashboard API proxies:
- Mutation requests to the Orchestrator (embed_orchestrator=false)
- SSE streams to the Gateway (embed_sse=false)

This lets the frontend talk to a single origin regardless of deployment mode.
"""

from __future__ import annotations

import os

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.responses import StreamingResponse

logger = structlog.stdlib.get_logger(__name__)


def mount_orchestrator_proxy(app: FastAPI) -> None:
    """Add catch-all proxy routes for orchestrator endpoints."""

    @app.api_route(
        "/api/pipeline/trigger",
        methods=["POST"],
        tags=["proxy"],
    )
    @app.api_route(
        "/api/pipeline/{cr_id}/intervene",
        methods=["POST"],
        tags=["proxy"],
    )
    @app.api_route(
        "/api/pipeline/{cr_id}/resume",
        methods=["POST"],
        tags=["proxy"],
    )
    @app.api_route(
        "/api/pipeline/{cr_id}/ci-result",
        methods=["POST"],
        tags=["proxy"],
    )
    @app.api_route(
        "/api/pipeline/{cr_id}/nudge",
        methods=["POST"],
        tags=["proxy"],
    )
    @app.api_route(
        "/api/pipeline/{cr_id}/release/approve",
        methods=["POST"],
        tags=["proxy"],
    )
    async def proxy_to_orchestrator(request: Request) -> Response:
        """Forward mutation request to the orchestrator."""
        client = request.app.state.orchestrator_client
        body = await request.body()
        path = request.url.path
        try:
            resp = await client.request(
                method=request.method,
                url=path,
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json"),
            )
        except Exception:
            logger.warning("orchestrator_proxy_failed", path=path, exc_info=True)
            return JSONResponse(
                content={"detail": "Orchestrator unavailable"},
                status_code=502,
            )


def mount_gateway_proxy(app: FastAPI) -> None:
    """Proxy SSE event streams to the gateway service."""
    import httpx

    gateway_url = os.environ.get(
        "HADRON_GATEWAY_URL",
        "http://hadron-gateway:8001",
    )

    @app.api_route(
        "/api/events/stream",
        methods=["GET"],
        tags=["proxy"],
    )
    @app.api_route(
        "/api/events/global-stream",
        methods=["GET"],
        tags=["proxy"],
    )
    async def proxy_to_gateway(request: Request) -> Response:
        """Forward SSE request to the gateway, streaming the response."""
        path = request.url.path
        query = str(request.url.query)
        url = f"{gateway_url}{path}"
        if query:
            url = f"{url}?{query}"
        try:
            client = httpx.AsyncClient(timeout=None)

            req = client.build_request("GET", url)
            resp = await client.send(req, stream=True)

            async def stream():
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()

            return StreamingResponse(
                stream(),
                status_code=resp.status_code,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception:
            logger.warning("gateway_proxy_failed", path=path, exc_info=True)
            return JSONResponse(
                content={"detail": "SSE Gateway unavailable"},
                status_code=502,
            )
