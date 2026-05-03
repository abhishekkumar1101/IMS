"""Debouncer — collapses N signals/window for the same component into one Work Item.

Algorithm (per assignment: "100 signals in 10 s → one Work Item"):

For each component_id we keep:
- a deque of recent timestamps (drop those older than `window_seconds`)
- a single-fire lock that expires at `window_end`, so only the *first*
  observation in a fresh window opens a Work Item.

This is a pure-Python, single-process implementation; the same behaviour
formerly lived on a Redis ZSET. Single-process is fine for the assignment;
multi-replica would re-implement on Redis.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Iterable


@dataclass
class DebounceResult:
    component_id: str
    freq_in_window: int
    should_create_work_item: bool


@dataclass
class _Entry:
    timestamps: deque  # of float seconds
    lock_expires_at: float = 0.0  # epoch seconds


class Debouncer:
    def __init__(self, redis=None, window_seconds: int = 10, threshold: int = 100) -> None:
        # `redis` arg kept for backwards-compatible kwargs in main.py wiring.
        self.window_seconds = window_seconds
        self.threshold = threshold
        self._by_component: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    async def observe_batch(self, component_ids: Iterable[str]) -> dict[str, DebounceResult]:
        unique = list({cid for cid in component_ids})
        if not unique:
            return {}
        now = time.time()
        cutoff = now - self.window_seconds

        async with self._lock:
            out: dict[str, DebounceResult] = {}
            for cid in unique:
                entry = self._by_component.get(cid)
                if entry is None:
                    entry = _Entry(timestamps=deque())
                    self._by_component[cid] = entry
                # Trim old timestamps
                while entry.timestamps and entry.timestamps[0] < cutoff:
                    entry.timestamps.popleft()
                # Add this observation
                entry.timestamps.append(now)
                # Decide whether to create a WI: claim the lock if expired.
                claimed = entry.lock_expires_at <= now
                if claimed:
                    entry.lock_expires_at = now + self.window_seconds
                out[cid] = DebounceResult(
                    component_id=cid,
                    freq_in_window=len(entry.timestamps),
                    should_create_work_item=claimed,
                )
            return out
