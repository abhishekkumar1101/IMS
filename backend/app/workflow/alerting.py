"""Alerting — Strategy pattern.

Each component severity is mapped to a different alert strategy. The strategy
encapsulates *how* to dispatch (page, slack, console). New strategies can be
swapped by editing `STRATEGY_REGISTRY` only — no caller changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Protocol

from app.models.schemas import ComponentKind, Severity
from app.storage.mongo import MongoStore

log = logging.getLogger("ims.alerting")


class AlertStrategy(Protocol):
    name: str

    async def send(self, *, work_item_id: str, severity: str, component_id: str, message: str) -> dict: ...


class P0PageStrategy:
    """P0 — page on-call. Stub logs to stdout + persists an alert row."""
    name = "page-oncall"

    async def send(self, *, work_item_id: str, severity: str, component_id: str, message: str) -> dict:
        log.warning("[ALERT P0 PAGE] component=%s wi=%s msg=%s", component_id, work_item_id, message)
        return {"channel": "pagerduty", "stub": True, "ack": False}


class P1SlackStrategy:
    """P1 — slack-channel ping. Stub."""
    name = "slack-channel"

    async def send(self, *, work_item_id: str, severity: str, component_id: str, message: str) -> dict:
        log.warning("[ALERT P1 SLACK] component=%s wi=%s msg=%s", component_id, work_item_id, message)
        return {"channel": "slack#oncall", "stub": True}


class P2ConsoleStrategy:
    """P2 — log only."""
    name = "console-log"

    async def send(self, *, work_item_id: str, severity: str, component_id: str, message: str) -> dict:
        log.info("[ALERT P2 LOG] component=%s wi=%s msg=%s", component_id, work_item_id, message)
        return {"channel": "stdout"}


class P3SilentStrategy:
    name = "silent"

    async def send(self, **kwargs) -> dict:
        return {"channel": "none", "suppressed": True}


# ----- Component → severity inference (rubric: "P0 for RDBMS, P2 for CACHE") -----

DEFAULT_SEVERITY: dict[ComponentKind, Severity] = {
    ComponentKind.RDBMS: Severity.P0,
    ComponentKind.MCP: Severity.P0,
    ComponentKind.NOSQL: Severity.P1,
    ComponentKind.QUEUE: Severity.P1,
    ComponentKind.API: Severity.P1,
    ComponentKind.CACHE: Severity.P2,
}


def severity_for(kind: ComponentKind, explicit: Severity | None = None) -> Severity:
    return explicit if explicit else DEFAULT_SEVERITY.get(kind, Severity.P2)


# ----- Strategy registry ---------------------------------------------------

STRATEGY_REGISTRY: dict[Severity, AlertStrategy] = {
    Severity.P0: P0PageStrategy(),
    Severity.P1: P1SlackStrategy(),
    Severity.P2: P2ConsoleStrategy(),
    Severity.P3: P3SilentStrategy(),
}


class AlertDispatcher:
    """Dispatcher selects the right strategy and persists the dispatch record."""

    def __init__(self, mongo: MongoStore) -> None:
        self.mongo = mongo

    async def dispatch(
        self,
        *,
        work_item_id: str,
        severity: Severity,
        component_id: str,
        message: str,
    ) -> dict:
        strategy = STRATEGY_REGISTRY.get(severity, STRATEGY_REGISTRY[Severity.P2])
        try:
            payload = await strategy.send(
                work_item_id=work_item_id, severity=severity.value,
                component_id=component_id, message=message,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("alert strategy %s failed", strategy.name)
            payload = {"error": str(e), "strategy": strategy.name}
        # Audit
        try:
            await self.mongo.db.alerts_dispatched.insert_one(
                {
                    "work_item_id": work_item_id,
                    "strategy": strategy.name,
                    "payload": payload,
                    "dispatched_at": datetime.now(timezone.utc),
                }
            )
        except Exception:
            log.warning("failed to persist alert audit", exc_info=True)
        return {"strategy": strategy.name, "payload": payload}
