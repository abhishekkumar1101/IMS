"""RCA submission — drives RESOLVED → CLOSED.

Mandatory-RCA invariant lives in `workflow.states.ResolvedState.close()`.
The router's job is just validation (Pydantic) + delegating to the workflow.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.models.schemas import RCAIn, RCAOut, WorkItemOut
from app.storage.repository import WorkItemRepo
from app.workflow.states import IllegalTransition
from app.workflow.transitions import WorkflowService

log = logging.getLogger("ims.api.rca")
router = APIRouter(prefix="/incidents", tags=["rca"])


@router.post("/{incident_id}/rca", response_model=WorkItemOut)
async def submit_rca(incident_id: UUID, rca: RCAIn, request: Request) -> WorkItemOut:
    repo = WorkItemRepo(request.app.state.mongo)
    svc = WorkflowService(repo)
    try:
        row = await svc.close_with_rca(incident_id, rca, actor=rca.submitted_by)
    except IllegalTransition as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))

    # Refresh with has_rca flag joined.
    fresh = await repo.get(incident_id) or row
    out = WorkItemOut(
        id=fresh["id"],
        component_id=fresh["component_id"],
        component_kind=fresh["component_kind"],
        severity=fresh["severity"],
        state=fresh["state"],
        title=fresh["title"],
        first_signal_at=fresh["first_signal_at"],
        last_signal_at=fresh["last_signal_at"],
        closed_at=fresh.get("closed_at"),
        mttr_seconds=fresh.get("mttr_seconds"),
        signal_count=fresh.get("signal_count", 0),
        summary=fresh.get("summary"),
        has_rca=True,
    )
    await request.app.state.dashboard_hub.broadcast({"type": "incident_closed", "incident": out.model_dump(mode="json")})
    return out


@router.get("/{incident_id}/rca", response_model=RCAOut)
async def get_rca(incident_id: UUID, request: Request) -> RCAOut:
    repo = WorkItemRepo(request.app.state.mongo)
    row = await repo.get_rca(incident_id)
    if row is None:
        raise HTTPException(404, "no RCA submitted")
    return RCAOut(
        root_cause_category=row["root_cause_category"],
        fix_applied=row["fix_applied"],
        prevention_steps=row["prevention_steps"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        submitted_by=row.get("submitted_by"),
        submitted_at=row["submitted_at"],
    )
