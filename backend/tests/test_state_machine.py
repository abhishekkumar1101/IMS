"""State pattern unit tests — every legal/illegal transition.

These tests don't touch a DB; they exercise `WorkItemContext` in pure memory
to prove the State pattern enforces the lifecycle correctly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.schemas import RCAIn
from app.workflow.states import (
    ClosedState,
    IllegalTransition,
    InvestigatingState,
    OpenState,
    ResolvedState,
    WorkItemContext,
)


def _ctx(state):
    return WorkItemContext(work_item_id="w1", state=state)


def _good_rca() -> RCAIn:
    now = datetime.now(timezone.utc)
    return RCAIn(
        root_cause_category="config-drift",
        fix_applied="Reverted bad migration and restarted the primary RDBMS replica.",
        prevention_steps="Add migration linter and a canary deploy gate before prod.",
        start_time=now - timedelta(minutes=10),
        end_time=now,
        submitted_by="oncall@example.com",
    )


# ---- Legal transitions ----------------------------------------------------

def test_open_to_investigating():
    ctx = _ctx(OpenState())
    ctx.investigate()
    assert ctx.state.name == "INVESTIGATING"


def test_investigating_to_resolved():
    ctx = _ctx(InvestigatingState())
    ctx.resolve()
    assert ctx.state.name == "RESOLVED"


def test_resolved_to_closed_with_complete_rca():
    ctx = _ctx(ResolvedState())
    ctx.close(_good_rca())
    assert ctx.state.name == "CLOSED"


def test_resolved_can_reopen_to_investigating():
    ctx = _ctx(ResolvedState())
    ctx.reopen()
    assert ctx.state.name == "INVESTIGATING"


def test_open_can_fast_forward_to_resolved():
    ctx = _ctx(OpenState())
    ctx.resolve()
    assert ctx.state.name == "RESOLVED"


# ---- Illegal transitions --------------------------------------------------

def test_open_cannot_close_directly():
    with pytest.raises(IllegalTransition):
        _ctx(OpenState()).close(_good_rca())


def test_investigating_cannot_close_directly():
    with pytest.raises(IllegalTransition):
        _ctx(InvestigatingState()).close(_good_rca())


def test_closed_is_terminal():
    ctx = _ctx(ClosedState())
    with pytest.raises(IllegalTransition):
        ctx.investigate()
    with pytest.raises(IllegalTransition):
        ctx.resolve()
    with pytest.raises(IllegalTransition):
        ctx.close(_good_rca())
    with pytest.raises(IllegalTransition):
        ctx.reopen()
