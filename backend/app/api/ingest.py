"""Signal ingestion endpoints.

POST /signals          — single signal (handy for curl & sample data)
POST /signals/batch    — batched ingest (recommended for high throughput)
WS   /signals/stream   — long-lived WebSocket; client sends JSON arrays.

All paths share the same flow:
  rate limit (Redis token bucket) → enqueue (bounded asyncio.Queue) → 202.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect, status

from app.core import metrics
from app.ingestion.queue import IngestQueueFull
from app.models.schemas import SignalBatchIn, SignalIn

log = logging.getLogger("ims.api.ingest")
router = APIRouter(tags=["ingest"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _check_rate_limit(request: Request, cost: int = 1) -> bool:
    bucket = request.app.state.rate_limiter
    allowed, _remaining = await bucket.consume(_client_key(request), cost=cost)
    return allowed


def _to_dict(s: SignalIn) -> dict[str, Any]:
    return s.model_dump(mode="python")


@router.post("/signals", status_code=status.HTTP_202_ACCEPTED)
async def post_signal(signal: SignalIn, request: Request, response: Response) -> dict:
    if not await _check_rate_limit(request):
        metrics.record_rejected()
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        response.headers["Retry-After"] = "1"
        return {"accepted": 0, "reason": "rate_limited"}
    try:
        request.app.state.queue.try_put([_to_dict(signal)])
    except IngestQueueFull:
        metrics.record_rejected()
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        response.headers["Retry-After"] = "1"
        return {"accepted": 0, "reason": "queue_full"}
    metrics.record_received()
    return {"accepted": 1}


@router.post("/signals/batch", status_code=status.HTTP_202_ACCEPTED)
async def post_signal_batch(batch: SignalBatchIn, request: Request, response: Response) -> dict:
    n = len(batch.signals)
    cost = max(1, n // 10)  # batch costs proportional to size
    if not await _check_rate_limit(request, cost=cost):
        metrics.record_rejected(n)
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        response.headers["Retry-After"] = "1"
        return {"accepted": 0, "reason": "rate_limited"}
    try:
        request.app.state.queue.try_put([_to_dict(s) for s in batch.signals])
    except IngestQueueFull:
        metrics.record_rejected(n)
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        response.headers["Retry-After"] = "1"
        return {"accepted": 0, "reason": "queue_full"}
    metrics.record_received(n)
    return {"accepted": n}


@router.websocket("/signals/stream")
async def ws_signals(ws: WebSocket) -> None:
    """Persistent WS for high-throughput producers.

    Send a JSON array of signal objects per message; receive `{accepted, queued}`.
    No rate-limit per message (the bounded queue + 429 channel handle that),
    but full queue triggers a `{accepted: 0, reason: 'queue_full'}` response so
    the client can back off.
    """
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            try:
                batch = SignalBatchIn(signals=data if isinstance(data, list) else [data])
            except Exception as e:  # noqa: BLE001
                await ws.send_json({"accepted": 0, "error": str(e)})
                continue
            try:
                ws.app.state.queue.try_put([_to_dict(s) for s in batch.signals])
                metrics.record_received(len(batch.signals))
                await ws.send_json({"accepted": len(batch.signals)})
            except IngestQueueFull:
                metrics.record_rejected(len(batch.signals))
                await ws.send_json({"accepted": 0, "reason": "queue_full"})
    except WebSocketDisconnect:
        return
