"""In-process token-bucket rate limiter.

Per-key (typically per-IP) bucket with capacity + refill rate. Uses an
asyncio lock per key to keep the CAS atomic without a database round-trip.
This is appropriate for a single-process deployment; for multi-replica we'd
swap in a Redis Lua bucket.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Tuple


@dataclass
class _Bucket:
    tokens: float
    last_ms: int


class InMemoryTokenBucket:
    def __init__(self, capacity: int, refill_per_sec: int) -> None:
        self.capacity = float(capacity)
        self.refill_per_sec = float(refill_per_sec)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def consume(self, key: str, cost: int = 1, now_ms: int | None = None) -> Tuple[bool, float]:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        async with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = _Bucket(tokens=self.capacity, last_ms=now_ms)
                self._buckets[key] = b
            delta_ms = max(0, now_ms - b.last_ms)
            b.tokens = min(self.capacity, b.tokens + (delta_ms / 1000.0) * self.refill_per_sec)
            b.last_ms = now_ms
            allowed = b.tokens >= cost
            if allowed:
                b.tokens -= cost
            return allowed, b.tokens
