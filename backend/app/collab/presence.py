"""In-memory presence registry — who is viewing which incident.

Single-process registry (good enough for the assignment's local Compose).
For multi-replica deployments, swap to a Redis-backed presence set with TTL.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Viewer:
    nickname: str
    avatar_color: str  # hex


class PresenceRegistry:
    def __init__(self) -> None:
        self._by_incident: dict[str, dict[str, Viewer]] = defaultdict(dict)  # incident_id -> conn_id -> Viewer
        self._lock = asyncio.Lock()

    async def join(self, incident_id: str, conn_id: str, nickname: str, color: str) -> list[Viewer]:
        async with self._lock:
            self._by_incident[incident_id][conn_id] = Viewer(nickname=nickname, avatar_color=color)
            return list(self._by_incident[incident_id].values())

    async def leave(self, incident_id: str, conn_id: str) -> list[Viewer]:
        async with self._lock:
            self._by_incident.get(incident_id, {}).pop(conn_id, None)
            return list(self._by_incident.get(incident_id, {}).values())

    def viewers(self, incident_id: str) -> list[Viewer]:
        return list(self._by_incident.get(incident_id, {}).values())
