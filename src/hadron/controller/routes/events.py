"""SSE event streaming endpoint."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from hadron.controller.dependencies import get_event_bus
from hadron.events.bus import EventBus

router = APIRouter(tags=["events"])


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
