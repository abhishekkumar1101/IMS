"""Pydantic schemas — wire format for API + WS."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ComponentKind(str, Enum):
    RDBMS = "RDBMS"
    MCP = "MCP"
    API = "API"
    CACHE = "CACHE"
    QUEUE = "QUEUE"
    NOSQL = "NOSQL"


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class IncidentState(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SignalIn(BaseModel):
    component_id: str = Field(..., min_length=1, max_length=128)
    component_kind: ComponentKind
    severity: Severity
    message: str = Field(..., min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None

    # Optional anomaly-detection feature inputs (graceful default if absent)
    latency_ms: float | None = None
    error_rate: float | None = None
    payload_size: int | None = None


class SignalBatchIn(BaseModel):
    signals: list[SignalIn]

    @field_validator("signals")
    @classmethod
    def non_empty(cls, v: list[SignalIn]) -> list[SignalIn]:
        if not v:
            raise ValueError("batch must contain at least one signal")
        if len(v) > 5000:
            raise ValueError("batch too large (max 5000)")
        return v


class WorkItemOut(BaseModel):
    id: UUID
    component_id: str
    component_kind: ComponentKind
    severity: Severity
    state: IncidentState
    title: str
    first_signal_at: datetime
    last_signal_at: datetime
    closed_at: datetime | None = None
    mttr_seconds: int | None = None
    signal_count: int
    summary: str | None = None
    has_rca: bool = False


class RCAIn(BaseModel):
    root_cause_category: str = Field(..., min_length=1, max_length=128)
    fix_applied: str = Field(..., min_length=10)
    prevention_steps: str = Field(..., min_length=10)
    start_time: datetime
    end_time: datetime
    submitted_by: str | None = None

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: datetime, info):
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class RCAOut(RCAIn):
    submitted_at: datetime


class StateTransitionIn(BaseModel):
    to_state: IncidentState
    actor: str | None = None


class CommentIn(BaseModel):
    author: str = Field(..., min_length=1, max_length=64)
    body: str = Field(..., min_length=1, max_length=4000)
    parent_id: str | None = None


class CommentOut(BaseModel):
    id: str
    incident_id: UUID
    author: str
    body: str
    parent_id: str | None
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    deps: dict[str, str]
    metrics: dict[str, Any]
