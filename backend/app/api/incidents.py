"""Incident (Work Item) routes — read & state transitions."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.models.schemas import IncidentState, StateTransitionIn, WorkItemOut
from app.storage.repository import WorkItemRepo
from app.workflow.states import IllegalTransition
from app.workflow.transitions import WorkflowService

log = logging.getLogger("ims.api.incidents")
router = APIRouter(prefix="/incidents", tags=["incidents"])


def _to_out(row: dict[str, Any]) -> WorkItemOut:
    return WorkItemOut(
        id=row["id"],
        component_id=row["component_id"],
        component_kind=row["component_kind"],
        severity=row["severity"],
        state=row["state"],
        title=row["title"],
        first_signal_at=row["first_signal_at"],
        last_signal_at=row["last_signal_at"],
        closed_at=row.get("closed_at"),
        mttr_seconds=row.get("mttr_seconds"),
        signal_count=row.get("signal_count", 0),
        summary=row.get("summary"),
        has_rca=bool(row.get("has_rca", False)),
    )


@router.get("", response_model=list[WorkItemOut])
async def list_incidents(request: Request, limit: int = 100) -> list[WorkItemOut]:
    repo = WorkItemRepo(request.app.state.mongo)
    rows = await repo.list_active(limit=limit)
    return [_to_out(r) for r in rows]


@router.get("/{incident_id}", response_model=WorkItemOut)
async def get_incident(incident_id: UUID, request: Request) -> WorkItemOut:
    repo = WorkItemRepo(request.app.state.mongo)
    row = await repo.get(incident_id)
    if row is None:
        raise HTTPException(404, "incident not found")
    return _to_out(row)


@router.get("/{incident_id}/signals")
async def list_signals(incident_id: UUID, request: Request, limit: int = 200) -> list[dict[str, Any]]:
    docs = await request.app.state.mongo.list_signals_for_incident(incident_id, limit=limit)
    # Strip Mongo internals + ensure JSON-serializable.
    out = []
    for d in docs:
        d.pop("_id", None)
        out.append(d)
    return out


@router.post("/{incident_id}/transition", response_model=WorkItemOut)
async def transition(incident_id: UUID, body: StateTransitionIn, request: Request) -> WorkItemOut:
    """OPEN → INVESTIGATING → RESOLVED. Use /rca for RESOLVED → CLOSED."""
    repo = WorkItemRepo(request.app.state.mongo)
    svc = WorkflowService(repo)
    try:
        if body.to_state == IncidentState.INVESTIGATING:
            # Same target state means two different transitions: from OPEN → investigate;
            # from RESOLVED → reopen. The State pattern accepts both, but we have to call
            # the right service method so the persistence layer's `from_state` filter matches.
            current = await repo.get(incident_id)
            if current is None:
                raise HTTPException(404, "incident not found")
            if current["state"] == "RESOLVED":
                row = await svc.reopen(incident_id, actor=body.actor)
            else:
                row = await svc.investigate(incident_id, actor=body.actor)
        elif body.to_state == IncidentState.RESOLVED:
            row = await svc.resolve(incident_id, actor=body.actor)
        elif body.to_state == IncidentState.CLOSED:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "use POST /incidents/{id}/rca to close (RCA required)",
            )
        else:
            raise HTTPException(400, f"unsupported transition target: {body.to_state}")
    except IllegalTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))

    # Notify dashboard subscribers.
    await request.app.state.dashboard_hub.broadcast(
        {"type": "incident_updated", "incident": _to_out(row).model_dump(mode="json")}
    )
    return _to_out(row)


@router.get("/{incident_id}/sparkline")
async def sparkline(incident_id: UUID, request: Request, minutes: int = 10) -> list[dict[str, Any]]:
    """Per-minute signal counts for the last N minutes (Live Feed sparkline)."""
    repo = WorkItemRepo(request.app.state.mongo)
    incident = await repo.get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    rows = await request.app.state.mongo.recent_metrics(component_id=incident["component_id"], minutes=minutes)
    # Bucket by minute.
    from collections import defaultdict

    buckets: dict[str, int] = defaultdict(int)
    for r in rows:
        # `bucket` is 5s; coalesce to minute keys.
        minute_key = r["bucket"].replace(second=0, microsecond=0).isoformat()
        buckets[minute_key] += int(r.get("signal_count", 0))
    return [{"t": t, "n": n} for t, n in sorted(buckets.items())]


@router.get("/{incident_id}/timeseries")
async def timeseries(incident_id: UUID, request: Request, minutes: int = 30) -> list[dict[str, Any]]:
    """Per-minute signals + anomalies for the incident detail chart."""
    repo = WorkItemRepo(request.app.state.mongo)
    incident = await repo.get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    rows = await request.app.state.mongo.recent_metrics(component_id=incident["component_id"], minutes=minutes)
    from collections import defaultdict

    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        minute_key = r["bucket"].replace(second=0, microsecond=0).isoformat()
        buckets[minute_key][0] += int(r.get("signal_count", 0))
        buckets[minute_key][1] += int(r.get("anomaly_count", 0))
    return [{"t": t, "signals": v[0], "anomalies": v[1]} for t, v in sorted(buckets.items())]


@router.post("/{incident_id}/summarize")
async def summarize(incident_id: UUID, request: Request) -> dict[str, Any]:
    """On-demand Gemini incident summary (used by Live Feed)."""
    summarizer = request.app.state.summarizer
    if not summarizer.is_configured:
        return {"summary": None, "reason": "gemini_not_configured"}

    repo = WorkItemRepo(request.app.state.mongo)
    cache = request.app.state.cache
    incident = await repo.get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")

    cached = await cache.get_cached_summary(str(incident_id), int(incident.get("summary_version", 0)))
    if cached:
        return {"summary": cached, "cached": True}

    signals = await request.app.state.mongo.list_signals_for_incident(incident_id, limit=8)
    summary = await summarizer.summarize(incident, signals)
    if summary:
        await repo.set_summary(incident_id, summary)
        await cache.set_cached_summary(str(incident_id), int(incident.get("summary_version", 0)) + 1, summary)
    return {"summary": summary, "cached": False}
