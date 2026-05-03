"""WebSocket endpoints — dashboard live feed + per-incident collab channel."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("ims.ws")
router = APIRouter(tags=["ws"])

_AVATAR_PALETTE = ["#22d3ee", "#a78bfa", "#f472b6", "#34d399", "#fbbf24", "#f87171", "#60a5fa"]


def _color_for(nick: str) -> str:
    return _AVATAR_PALETTE[abs(hash(nick)) % len(_AVATAR_PALETTE)]


@router.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket) -> None:
    """Live feed channel — pushes incident_updated/closed events.

    Server periodically pushes the dashboard cache snapshot every 2s as a heartbeat.
    """
    await ws.accept()
    hub = ws.app.state.dashboard_hub
    cache = ws.app.state.cache
    await hub.attach(ws)

    async def heartbeat() -> None:
        try:
            while True:
                snapshot = await cache.list_dashboard_incidents()
                await ws.send_json({"type": "snapshot", "incidents": [json.loads(s) for s in snapshot]})
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            return
        except Exception:
            return

    hb_task = asyncio.create_task(heartbeat())
    try:
        while True:
            await ws.receive_text()  # ignore inbound; clients only listen
    except WebSocketDisconnect:
        pass
    finally:
        hb_task.cancel()
        await hub.detach(ws)


@router.websocket("/ws/incidents/{incident_id}")
async def ws_incident(ws: WebSocket, incident_id: str) -> None:
    """Collab channel — presence + comment broadcasts for one incident."""
    await ws.accept()
    presence = ws.app.state.presence
    hub = ws.app.state.incident_hub
    conn_id = str(uuid4())

    # First message must be {type: 'hello', nickname: '...'}.
    nickname = "anon"
    try:
        first = await ws.receive_json()
        if isinstance(first, dict) and first.get("type") == "hello":
            nickname = (first.get("nickname") or "anon").strip()[:32] or "anon"
    except Exception:
        pass

    color = _color_for(nickname)
    viewers = await presence.join(incident_id, conn_id, nickname, color)
    await hub.attach(incident_id, ws)
    await hub.broadcast(
        incident_id,
        {"type": "presence", "viewers": [v.__dict__ for v in viewers]},
    )

    try:
        while True:
            data: Any = await ws.receive_json()
            kind = data.get("type") if isinstance(data, dict) else None
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "typing":
                await hub.broadcast(incident_id, {"type": "typing", "nickname": nickname})
    except WebSocketDisconnect:
        pass
    finally:
        viewers = await presence.leave(incident_id, conn_id)
        await hub.detach(incident_id, ws)
        await hub.broadcast(
            incident_id,
            {"type": "presence", "viewers": [v.__dict__ for v in viewers]},
        )
