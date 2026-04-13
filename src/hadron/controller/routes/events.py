"""SSE event streaming endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette.sse import EventSourceResponse

from hadron.controller.dependencies import get_event_bus, get_session_factory
from hadron.db.models import CRRun
from hadron.events.bus import EventBus
from hadron.models.events import PipelineEvent

router = APIRouter(tags=["events"])


# ---------------------------------------------------------------------------
# Per-CR stream
# ---------------------------------------------------------------------------


async def _event_generator(
    request: Request, cr_id: str, event_bus: EventBus, last_event_id: str = "0",
) -> AsyncIterator[dict]:
    """Generate SSE events from Redis stream for a CR.

    Supports ``Last-Event-ID`` so that ``EventSource`` auto-reconnects resume
    from the last received event instead of replaying everything.
    """
    # Replay from after the last event the client already received
    events, last_id = await event_bus.replay(cr_id, from_id=last_event_id)
    for event, stream_id in events:
        yield {
            "event": event.event_type.value,
            "data": event.model_dump_json(),
            "id": stream_id,
        }

    # Subscribe from the last replayed ID so events emitted during replay aren't lost
    async for event, stream_id in event_bus.subscribe(cr_id, last_id=last_id):
        if await request.is_disconnected():
            break
        yield {
            "event": event.event_type.value,
            "data": event.model_dump_json(),
            "id": stream_id,
        }

        # Stop streaming after terminal events
        if event.event_type.value in ("pipeline_completed", "pipeline_failed"):
            break


@router.get("/events/stream")
async def event_stream(
    cr_id: str,
    request: Request,
    event_bus: EventBus = Depends(get_event_bus),
) -> EventSourceResponse:
    """SSE endpoint for real-time pipeline events."""
    last_event_id = request.headers.get("Last-Event-ID", "0")
    return EventSourceResponse(
        _event_generator(request, cr_id, event_bus, last_event_id)
    )


# ---------------------------------------------------------------------------
# Global stream — activity across all active CRs
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = ("running", "paused", "pending")


async def _infer_current_stage(
    cr_id: str, event_bus: EventBus,
) -> str:
    """Best-effort: replay events and return the last stage_entered stage."""
    events, _ = await event_bus.replay(cr_id)
    stage = ""
    for event, _ in events:
        if event.event_type.value == "stage_entered" and event.stage:
            stage = event.stage
    return stage


async def _global_event_generator(
    request: Request,
    event_bus: EventBus,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[dict]:
    """Stream activity across all active CRs.

    1. Sends ``cr_status`` snapshots for every active CR.
    2. Multiplexes live events from all active CR streams.
    """
    # Discover active CRs
    async with session_factory() as session:
        result = await session.execute(
            select(CRRun).where(CRRun.status.in_(_ACTIVE_STATUSES))
        )
        active_crs = list(result.scalars().all())

    # Send initial snapshots
    for cr in active_crs:
        if await request.is_disconnected():
            return
        title = ""
        if cr.raw_cr_json:
            title = cr.raw_cr_json.get("title", "")
        stage = await _infer_current_stage(cr.cr_id, event_bus)
        yield {
            "event": "cr_status",
            "data": json.dumps({
                "cr_id": cr.cr_id,
                "title": title,
                "stage": stage,
                "status": cr.status,
            }),
        }

    if not active_crs:
        # Keep connection alive — client shows empty state
        while not await request.is_disconnected():
            await asyncio.sleep(5)
        return

    # Multiplex live events from all active CR streams.
    # Each CR gets its own subscriber task pushing into a shared queue.
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _subscribe_cr(cr_id: str) -> None:
        try:
            async for event, stream_id in event_bus.subscribe(cr_id, last_id="$"):
                await queue.put({
                    "event": event.event_type.value,
                    "data": event.model_dump_json(),
                    "id": f"{cr_id}:{stream_id}",
                })
        except asyncio.CancelledError:
            pass

    tasks = [asyncio.create_task(_subscribe_cr(cr.cr_id)) for cr in active_crs]

    try:
        while not await request.is_disconnected():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=5.0)
                yield item
            except asyncio.TimeoutError:
                continue
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@router.get("/events/global-stream")
async def global_event_stream(
    request: Request,
    event_bus: EventBus = Depends(get_event_bus),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EventSourceResponse:
    """SSE endpoint for real-time activity across all active CRs."""
    return EventSourceResponse(
        _global_event_generator(request, event_bus, session_factory)
    )
