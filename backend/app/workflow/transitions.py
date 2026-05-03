"""High-level orchestration of state transitions.

Glues the State pattern (`workflow.states`) to persistence (`storage.repository`)
inside a single transactional unit. Routers should call these helpers, not the
repo directly, so the State pattern stays authoritative.
"""
from __future__ import annotations

from uuid import UUID

from app.models.schemas import IncidentState, RCAIn
from app.storage.repository import WorkItemRepo
from app.workflow.states import (
    ClosedState,
    IllegalTransition,
    InvestigatingState,
    OpenState,
    ResolvedState,
    WorkItemContext,
    state_from_name,
)


class WorkflowService:
    def __init__(self, repo: WorkItemRepo) -> None:
        self.repo = repo

    async def _load(self, wi_id: UUID) -> WorkItemContext:
        row = await self.repo.get(wi_id)
        if row is None:
            raise IllegalTransition("work_item not found")
        return WorkItemContext(work_item_id=str(wi_id), state=state_from_name(row["state"]))

    async def investigate(self, wi_id: UUID, actor: str | None = None) -> dict:
        ctx = await self._load(wi_id)
        ctx.investigate()  # raises IllegalTransition if not allowed
        await self.repo.update_state(wi_id, "OPEN", IncidentState.INVESTIGATING.value, actor=actor)
        return await self.repo.get(wi_id)  # type: ignore[return-value]

    async def resolve(self, wi_id: UUID, actor: str | None = None) -> dict:
        ctx = await self._load(wi_id)
        prior = ctx.state.name
        ctx.resolve()
        await self.repo.update_state(wi_id, prior, IncidentState.RESOLVED.value, actor=actor)
        return await self.repo.get(wi_id)  # type: ignore[return-value]

    async def reopen(self, wi_id: UUID, actor: str | None = None) -> dict:
        ctx = await self._load(wi_id)
        ctx.reopen()
        await self.repo.update_state(wi_id, "RESOLVED", IncidentState.INVESTIGATING.value, actor=actor)
        return await self.repo.get(wi_id)  # type: ignore[return-value]

    async def close_with_rca(self, wi_id: UUID, rca: RCAIn, actor: str | None = None) -> dict:
        """Validates with the State pattern *and* persists in one TX.

        The State pattern raises before we touch the DB — so an invalid
        RCA never reaches Postgres. The repo handles the atomic write.
        """
        ctx = await self._load(wi_id)
        ctx.close(rca)  # raises IllegalTransition if invalid

        return await self.repo.close_with_rca(wi_id, rca, actor=actor)
