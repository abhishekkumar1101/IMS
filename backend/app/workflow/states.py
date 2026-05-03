"""Work Item lifecycle — implemented as a classic State pattern.

States: OPEN → INVESTIGATING → RESOLVED → CLOSED.
- `close()` requires a complete RCA on the context.
- `IllegalTransition` is raised for any move not allowed by the current state.
- The state object encapsulates the rules; the WorkItemContext exposes the API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.models.schemas import IncidentState, RCAIn


class IllegalTransition(Exception):
    """Raised when a transition is not allowed by the current state."""


@dataclass
class WorkItemContext:
    """Lightweight in-memory model the state machine operates on.

    Persistence is delegated — call `apply` after any successful transition.
    """
    work_item_id: str
    state: "IncidentState_"
    rca: Optional[RCAIn] = None
    actor: Optional[str] = None
    transitions: list[tuple[str, str]] = field(default_factory=list)

    def transition_to(self, target: "IncidentState_") -> None:
        self.transitions.append((self.state.name, target.name))
        self.state = target

    # State-pattern delegate methods --------------------------------------
    def investigate(self) -> None:
        self.state.investigate(self)

    def resolve(self) -> None:
        self.state.resolve(self)

    def close(self, rca: RCAIn) -> None:
        # Attach RCA to context; ClosedState validates it on transition.
        self.rca = rca
        self.state.close(self)

    def reopen(self) -> None:
        self.state.reopen(self)


class IncidentState_(ABC):
    """Abstract State."""
    name: str = ""

    def investigate(self, ctx: WorkItemContext) -> None:
        raise IllegalTransition(f"cannot investigate from {self.name}")

    def resolve(self, ctx: WorkItemContext) -> None:
        raise IllegalTransition(f"cannot resolve from {self.name}")

    def close(self, ctx: WorkItemContext) -> None:
        raise IllegalTransition(f"cannot close from {self.name}")

    def reopen(self, ctx: WorkItemContext) -> None:
        raise IllegalTransition(f"cannot reopen from {self.name}")


class OpenState(IncidentState_):
    name = IncidentState.OPEN.value

    def investigate(self, ctx: WorkItemContext) -> None:
        ctx.transition_to(InvestigatingState())

    def resolve(self, ctx: WorkItemContext) -> None:
        # Permit fast-forwarding from OPEN → RESOLVED for trivial incidents.
        ctx.transition_to(ResolvedState())


class InvestigatingState(IncidentState_):
    name = IncidentState.INVESTIGATING.value

    def resolve(self, ctx: WorkItemContext) -> None:
        ctx.transition_to(ResolvedState())


class ResolvedState(IncidentState_):
    name = IncidentState.RESOLVED.value

    def close(self, ctx: WorkItemContext) -> None:
        rca = ctx.rca
        if rca is None:
            raise IllegalTransition("RCA is required to close an incident")
        # Pydantic already validates field presence + lengths; this is defense in depth.
        for field_ in ("root_cause_category", "fix_applied", "prevention_steps"):
            if not getattr(rca, field_):
                raise IllegalTransition(f"RCA.{field_} is required to close")
        if rca.end_time <= rca.start_time:
            raise IllegalTransition("RCA.end_time must be after start_time")
        ctx.transition_to(ClosedState())

    def reopen(self, ctx: WorkItemContext) -> None:
        ctx.transition_to(InvestigatingState())


class ClosedState(IncidentState_):
    """Terminal state — no further transitions permitted."""
    name = IncidentState.CLOSED.value


_BY_NAME = {s.name: s for s in [OpenState(), InvestigatingState(), ResolvedState(), ClosedState()]}


def state_from_name(name: str) -> IncidentState_:
    try:
        return _BY_NAME[name]
    except KeyError as e:
        raise IllegalTransition(f"unknown state: {name}") from e
