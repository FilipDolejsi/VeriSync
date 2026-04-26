import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-user event queues: user_id -> list of active queues (one per browser tab)
_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


# ── Publisher (called by the pipeline and webhook handler) ────────────────────

async def publish(user_id: str, event: dict):
    """Send an event to all active SSE connections for a user."""
    dead = []
    # Snapshot the list so concurrent removals by _event_stream don't cause issues
    for q in list(_queues[user_id]):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _queues[user_id].remove(q)
        except ValueError:
            pass  # already removed by a concurrent _event_stream teardown


# ── SSE stream ────────────────────────────────────────────────────────────────

async def _event_stream(user_id: str, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        try:
            _queues[user_id].remove(queue)
        except ValueError:
            pass  # already removed by a concurrent publish cleanup
        logger.info(f"SSE connection closed for user {user_id}")


@router.get("/events")
async def events(request: Request):
    from auth.github_oauth import get_current_user
    user = await get_current_user(request)
    if not user:
        return StreamingResponse(
            iter(["data: {\"type\": \"error\", \"detail\": \"unauthenticated\"}\n\n"]),
            media_type="text/event-stream",
        )

    user_id = user["id"]
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues[user_id].append(queue)
    logger.info(f"SSE connection opened for user {user_id}")

    return StreamingResponse(
        _event_stream(user_id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering
        },
    )
