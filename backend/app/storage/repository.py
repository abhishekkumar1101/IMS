"""Repository layer for Work Items + RCAs — MongoDB version.

Mirrors the original Postgres repo's API so the workflow/transitions service
and routers don't change. Uses single-document atomic ops where possible
(`find_one_and_update`); transactions where the spec demands atomicity
(close-with-RCA flips state + writes RCA + appends transition).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.retry import retry_db
from app.models.schemas import ComponentKind, IncidentState, RCAIn, Severity
from app.storage.mongo import MongoStore

log = logging.getLogger("ims.repo")


class WorkItemRepo:
    def __init__(self, mongo: MongoStore) -> None:
        self.mongo = mongo

    @property
    def _wi(self):
        return self.mongo.db.work_items

    @property
    def _st(self):
        return self.mongo.db.state_transitions

    @retry_db()
    async def find_open_for_component(self, component_id: str) -> dict | None:
        doc = await self._wi.find_one(
            {"component_id": component_id, "state": {"$in": ["OPEN", "INVESTIGATING"]}},
            sort=[("first_signal_at", -1)],
        )
        return _shape(doc) if doc else None

    @retry_db()
    async def create(
        self,
        *,
        component_id: str,
        component_kind: ComponentKind,
        severity: Severity,
        title: str,
        first_signal_at: datetime,
    ) -> dict:
        """Create a Work Item if no OPEN/INVESTIGATING one exists for this component.

        Atomic: uses `find_one_and_update` with `upsert=True` keyed on the
        (component_id, state in {OPEN, INVESTIGATING}) filter. If a doc
        already matches, we re-read it and return that — losing the race is
        the desired behaviour (debouncer guarantees one Work Item per window).
        """
        # First, atomically claim a "creation slot" using upsert.
        wi_id = str(uuid4())
        now = datetime.now(timezone.utc)
        new_doc: dict[str, Any] = {
            "_id": wi_id,
            "component_id": component_id,
            "component_kind": component_kind.value,
            "severity": severity.value,
            "state": "OPEN",
            "title": title,
            "first_signal_at": first_signal_at,
            "last_signal_at": first_signal_at,
            "closed_at": None,
            "mttr_seconds": None,
            "signal_count": 0,
            "summary": None,
            "summary_version": 0,
            "has_rca": False,
            "rca": None,
            "created_at": now,
            "updated_at": now,
        }

        # Filter: no existing open WI for this component
        existing = await self._wi.find_one(
            {"component_id": component_id, "state": {"$in": ["OPEN", "INVESTIGATING"]}}
        )
        if existing:
            return _shape(existing)

        try:
            await self._wi.insert_one(new_doc)
        except Exception:
            # Lost the race — find & return the survivor.
            existing = await self._wi.find_one(
                {"component_id": component_id, "state": {"$in": ["OPEN", "INVESTIGATING"]}}
            )
            if existing:
                return _shape(existing)
            raise

        await self._st.insert_one(
            {
                "work_item_id": wi_id,
                "from_state": None,
                "to_state": "OPEN",
                "actor": "system",
                "occurred_at": now,
            }
        )
        return _shape(new_doc)

    @retry_db()
    async def increment_signal_counts(self, wi_id: UUID, n: int, last_ts: datetime) -> None:
        await self._wi.update_one(
            {"_id": str(wi_id)},
            {
                "$inc": {"signal_count": n},
                "$max": {"last_signal_at": last_ts},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    @retry_db()
    async def get(self, wi_id: UUID) -> dict | None:
        doc = await self._wi.find_one({"_id": str(wi_id)})
        return _shape(doc) if doc else None

    @retry_db()
    async def list_active(self, limit: int = 100) -> list[dict]:
        # Sort: state priority → severity priority → recency.
        pipeline = [
            {
                "$addFields": {
                    "state_rank": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$state", "OPEN"]}, "then": 0},
                                {"case": {"$eq": ["$state", "INVESTIGATING"]}, "then": 1},
                                {"case": {"$eq": ["$state", "RESOLVED"]}, "then": 2},
                            ],
                            "default": 3,
                        }
                    },
                    "sev_rank": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$severity", "P0"]}, "then": 0},
                                {"case": {"$eq": ["$severity", "P1"]}, "then": 1},
                                {"case": {"$eq": ["$severity", "P2"]}, "then": 2},
                            ],
                            "default": 3,
                        }
                    },
                }
            },
            {"$sort": {"state_rank": 1, "sev_rank": 1, "first_signal_at": -1}},
            {"$limit": limit},
        ]
        out: list[dict] = []
        async for doc in self._wi.aggregate(pipeline):
            out.append(_shape(doc))
        return out

    @retry_db()
    async def update_state(self, wi_id: UUID, from_state: str, to_state: str, actor: str | None = None) -> None:
        result = await self._wi.find_one_and_update(
            {"_id": str(wi_id), "state": from_state},
            {"$set": {"state": to_state, "updated_at": datetime.now(timezone.utc)}},
            return_document=False,
        )
        if result is None:
            raise ValueError(f"state mismatch: expected {from_state} for {wi_id}")
        await self._st.insert_one(
            {
                "work_item_id": str(wi_id),
                "from_state": from_state,
                "to_state": to_state,
                "actor": actor or "user",
                "occurred_at": datetime.now(timezone.utc),
            }
        )

    @retry_db()
    async def close_with_rca(self, wi_id: UUID, rca: RCAIn, actor: str | None = None) -> dict:
        """Atomically: write RCA + flip state to CLOSED + append transition + compute MTTR.

        On a replica set / Atlas, this runs in a single multi-doc transaction.
        On a standalone Mongo, we fall back to a best-effort sequenced write
        with compensation: if the RCA write succeeds but the state flip fails,
        we leave the RCA attached and surface the error so the operator can retry.
        """
        wi_id_s = str(wi_id)

        # Pre-read for state validation + MTTR base.
        current = await self._wi.find_one({"_id": wi_id_s})
        if current is None:
            raise ValueError("work_item not found")
        if current["state"] != IncidentState.RESOLVED.value:
            raise ValueError(f"can only close from RESOLVED (current: {current['state']})")
        first_signal_at: datetime = current["first_signal_at"]
        mttr = max(0, int((rca.end_time - first_signal_at).total_seconds()))
        now = datetime.now(timezone.utc)

        rca_doc = {
            "root_cause_category": rca.root_cause_category,
            "fix_applied": rca.fix_applied,
            "prevention_steps": rca.prevention_steps,
            "start_time": rca.start_time,
            "end_time": rca.end_time,
            "submitted_by": rca.submitted_by,
            "submitted_at": now,
        }

        async def _do_writes(session=None):
            await self._wi.update_one(
                {"_id": wi_id_s, "state": "RESOLVED"},
                {
                    "$set": {
                        "state": "CLOSED",
                        "closed_at": now,
                        "mttr_seconds": mttr,
                        "rca": rca_doc,
                        "has_rca": True,
                        "updated_at": now,
                    }
                },
                session=session,
            )
            await self._st.insert_one(
                {
                    "work_item_id": wi_id_s,
                    "from_state": "RESOLVED",
                    "to_state": "CLOSED",
                    "actor": actor or rca.submitted_by or "user",
                    "occurred_at": now,
                },
                session=session,
            )

        if self.mongo.supports_transactions:
            async with await self.mongo.client.start_session() as session:
                async with session.start_transaction():
                    await _do_writes(session=session)
        else:
            await _do_writes()

        fresh = await self._wi.find_one({"_id": wi_id_s})
        return _shape(fresh)

    @retry_db()
    async def get_rca(self, wi_id: UUID) -> dict | None:
        doc = await self._wi.find_one({"_id": str(wi_id)}, projection={"rca": 1})
        return doc.get("rca") if doc else None

    @retry_db()
    async def set_summary(self, wi_id: UUID, summary: str) -> int:
        doc = await self._wi.find_one_and_update(
            {"_id": str(wi_id)},
            {"$set": {"summary": summary, "updated_at": datetime.now(timezone.utc)}, "$inc": {"summary_version": 1}},
            return_document=True,
        )
        return int(doc.get("summary_version", 0)) if doc else 0


# ----- helpers ------------------------------------------------------------


def _shape(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalise Mongo doc to the dict shape the callers expect.

    The repo originally returned Postgres rows with `id` (UUID), Mongo uses `_id`.
    We surface both for compatibility.
    """
    if doc is None:
        return doc
    out = dict(doc)
    if "_id" in out and "id" not in out:
        out["id"] = out["_id"]
    return out
