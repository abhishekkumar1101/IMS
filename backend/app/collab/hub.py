"""Per-incident WebSocket fan-out hub.

Each incident detail page joins a hub; broadcasts (presence updates +
new comments) are pushed to all sockets on the same incident.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class IncidentHub:
    def __init__(self) -> None:
        self._sockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def attach(self, incident_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets[incident_id].add(ws)

    async def detach(self, incident_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets[incident_id].discard(ws)

    async def broadcast(self, incident_id: str, event: dict[str, Any]) -> None:
        msg = json.dumps(event, default=str)
        async with self._lock:
            sockets = list(self._sockets.get(incident_id, set()))
        for ws in sockets:
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                # Swallow broken sockets; cleanup on next iteration.
                pass


class DashboardHub:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def attach(self, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets.add(ws)

    async def detach(self, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        msg = json.dumps(event, default=str)
        async with self._lock:
            sockets = list(self._sockets)
        for ws in sockets:
            try:
                await ws.send_text(msg)
            except Exception:
                pass
