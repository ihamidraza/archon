"""In-process publish/subscribe so a customer's live stream receives an agent's reply.

When a thread escalates, the customer's ``/chat`` stream ends (the graph paused). Their
browser then opens ``POST /threads/{id}/stream`` and **subscribes** here. Later, when a human
agent replies via ``/resume`` (in a different request, possibly a different browser), that
request **publishes** each SSE event to the thread's subscribers — so the reply streams into
the waiting customer's chat in real time.

This is a plain asyncio fan-out: one process, one event loop, ``asyncio.Queue`` per
subscriber. See the single-process caveat in ``escalation_registry`` — the durable
cross-worker equivalent would be Redis pub/sub.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import BaseModel


class ThreadPubSub:
    """Fan-out of SSE event models to per-thread subscribers (single-process)."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[BaseModel]]] = {}

    @asynccontextmanager
    async def subscribe(self, thread_id: str) -> AsyncIterator[asyncio.Queue[BaseModel]]:
        """Register a subscriber queue for ``thread_id``; cleaned up on exit."""
        queue: asyncio.Queue[BaseModel] = asyncio.Queue()
        self._subs.setdefault(thread_id, set()).add(queue)
        try:
            yield queue
        finally:
            subs = self._subs.get(thread_id)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    self._subs.pop(thread_id, None)

    async def publish(self, thread_id: str, event: BaseModel) -> None:
        """Deliver ``event`` to every current subscriber of ``thread_id`` (no-op if none)."""
        for queue in tuple(self._subs.get(thread_id, ())):
            queue.put_nowait(event)


# Shared singleton, imported by the API routes.
pubsub = ThreadPubSub()
