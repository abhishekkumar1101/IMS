"""Bounded asyncio queue — the heart of our backpressure strategy.

When the queue is full, the HTTP handler returns **HTTP 429** instead of
blocking, so a slow persistence layer cannot crash the producer or balloon
memory. The queue stores raw signal *dicts* (already validated by Pydantic).
"""
from __future__ import annotations

import asyncio
from typing import Any


class IngestQueueFull(Exception):
    """Raised when `try_put` cannot enqueue (caller should respond 429)."""


class IngestQueue:
    def __init__(self, maxsize: int) -> None:
        self._q: asyncio.Queue[list[dict[str, Any]]] = asyncio.Queue(maxsize=maxsize)
        self.maxsize = maxsize

    def try_put(self, batch: list[dict[str, Any]]) -> None:
        try:
            self._q.put_nowait(batch)
        except asyncio.QueueFull as e:
            raise IngestQueueFull() from e

    async def get(self) -> list[dict[str, Any]]:
        return await self._q.get()

    def task_done(self) -> None:
        self._q.task_done()

    def size(self) -> int:
        return self._q.qsize()

    def is_full(self) -> bool:
        return self._q.full()
