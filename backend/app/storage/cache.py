"""In-process cache — replaces the Redis hot-path.

Holds:
- `dashboard:state` — incident snapshots keyed by work_item_id.
- `summary:{wi}:{ver}` — Gemini summary results, with TTL.

Single-process; appropriate for the assignment's single-node setup.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class _TTLEntry:
    value: str
    expires_at: float


class InMemoryCache:
    def __init__(self) -> None:
        self._dashboard: dict[str, str] = {}
        self._ttl: dict[str, _TTLEntry] = {}
        self._lock = asyncio.Lock()

    async def ping(self) -> str:
        return "ok"

    # ---- dashboard ------------------------------------------------------

    async def upsert_dashboard_incident(self, work_item_id: str, payload: str) -> None:
        async with self._lock:
            self._dashboard[work_item_id] = payload

    async def remove_dashboard_incident(self, work_item_id: str) -> None:
        async with self._lock:
            self._dashboard.pop(work_item_id, None)

    async def list_dashboard_incidents(self) -> list[str]:
        async with self._lock:
            return list(self._dashboard.values())

    # ---- TTL cache ------------------------------------------------------

    async def get_cached_summary(self, work_item_id: str, version: int) -> str | None:
        key = f"summary:{work_item_id}:{version}"
        now = time.monotonic()
        async with self._lock:
            entry = self._ttl.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._ttl.pop(key, None)
                return None
            return entry.value

    async def set_cached_summary(self, work_item_id: str, version: int, summary: str, ttl: int = 300) -> None:
        key = f"summary:{work_item_id}:{version}"
        async with self._lock:
            self._ttl[key] = _TTLEntry(value=summary, expires_at=time.monotonic() + ttl)
