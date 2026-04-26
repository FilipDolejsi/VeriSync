"""
dashboard/events.py
───────────────────
Server-Sent Events broker + endpoint for the live dashboard feed.

Pipeline code publishes events with `await events.publish(user_id, "finding", {...})`.
The browser subscribes via EventSource("/events/stream") and receives only
events scoped to the authenticated user.

Event types emitted:
    - balance  { balance: int, delta: int }
    - webhook  { event, repo, pr_number }
    - chunk    { count, languages: [str] }
    - route    { summary, models: [str] }
    - finding  { severity, category, description, model_id }
    - report   { pr_number, repo, pr_url, total_cost_sats,
                 critical_count, warning_count, info_count, title }
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from auth.github_oauth import get_current_user  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter()


class EventBroker:
    """In-process pub/sub keyed by user_id. One queue per active connection."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subs[user_id].add(q)
        return q

    async def unsubscribe(self, user_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subs[user_id].discard(q)
            if not self._subs[user_id]:
                self._subs.pop(user_id, None)

    async def publish(self, user_id: str, event: str, payload: dict[str, Any]) -> None:
        """Fan out to every queue belonging to user_id. Drop on backpressure."""
        async with self._lock:
            queues = list(self._subs.get(user_id, ()))
        for q in queues:
            try:
                q.put_nowait((event, payload))
            except asyncio.QueueFull:
                logger.warning("SSE queue full for user=%s; dropping event=%s", user_id, event)


broker = EventBroker()


def _format_sse(event: str, data: dict[str, Any]) -> str:
    """SSE wire format: event/data lines terminated by a blank line."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def _stream(request: Request, user_id: str) -> AsyncIterator[str]:
    q = await broker.subscribe(user_id)
    try:
        # Initial hello so the browser sees the connection open immediately.
        yield _format_sse("hello", {"user_id": user_id})

        while True:
            if await request.is_disconnected():
                return
            try:
                event, payload = await asyncio.wait_for(q.get(), timeout=15.0)
                yield _format_sse(event, payload)
            except asyncio.TimeoutError:
                # Heartbeat keeps proxies from killing the connection.
                yield ": ping\n\n"
    finally:
        await broker.unsubscribe(user_id, q)


@router.get("/events/stream")
async def event_stream(request: Request, user=Depends(get_current_user)):
    return StreamingResponse(
        _stream(request, user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
