"""MongoDB client — central store for everything in this Mongo-only build.

Collections:
- `signals`           — every raw signal (Data Lake / audit log)
- `work_items`        — Source of Truth (transitions, RCA embedded, MTTR)
- `state_transitions` — append-only audit of every state change
- `alerts_dispatched` — strategy-pattern alert audit
- `signal_metrics`    — time-series collection (5 s buckets per (component, severity))
- `comments`          — collab comments per incident

MongoDB transactions used where the spec calls for atomicity (RCA + state
flip on close). Single-document ops are atomic by default.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.retry import retry_db

log = logging.getLogger("ims.mongo")


class MongoStore:
    def __init__(self, uri: str, db_name: str) -> None:
        self._uri = uri
        self._db_name = db_name
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None
        self.supports_transactions: bool = False

    async def connect(self) -> None:
        # Server selection timeout kept short so failures surface fast.
        self._client = AsyncIOMotorClient(self._uri, serverSelectionTimeoutMS=8000)
        # Use the default DB embedded in the URI if present, else fall back.
        default_db = self._client.get_default_database() if "/" in self._uri.split("://", 1)[-1] else None
        self._db = default_db if default_db is not None and default_db.name else self._client[self._db_name]

        # Ping
        await self._client.admin.command("ping")

        # Detect replica set (transactions supported on RS / Atlas).
        try:
            hello = await self._client.admin.command("hello")
            self.supports_transactions = bool(hello.get("setName") or hello.get("isWritablePrimary"))
            # 'hello' returns isWritablePrimary even on standalone; check setName for RS.
            self.supports_transactions = bool(hello.get("setName"))
        except Exception:
            self.supports_transactions = False

        # Indexes (idempotent).
        await self._db.signals.create_index([("component_id", ASCENDING), ("created_at", DESCENDING)])
        await self._db.signals.create_index([("work_item_id", ASCENDING)])
        await self._db.signals.create_index([("anomaly_score", ASCENDING)])

        await self._db.work_items.create_index([("state", ASCENDING), ("severity", ASCENDING)])
        await self._db.work_items.create_index([("component_id", ASCENDING), ("state", ASCENDING)])
        await self._db.work_items.create_index([("first_signal_at", DESCENDING)])

        await self._db.state_transitions.create_index([("work_item_id", ASCENDING), ("occurred_at", ASCENDING)])
        await self._db.alerts_dispatched.create_index([("work_item_id", ASCENDING)])
        await self._db.comments.create_index([("incident_id", ASCENDING), ("created_at", ASCENDING)])

        # Time-series collection — best-effort; older Mongo versions or shared clusters may not allow.
        try:
            existing = set(await self._db.list_collection_names())
            if "signal_metrics" not in existing:
                await self._db.create_collection(
                    "signal_metrics",
                    timeseries={"timeField": "bucket", "metaField": "meta", "granularity": "seconds"},
                )
        except Exception as e:  # noqa: BLE001
            # Atlas free tier sometimes restricts time-series; fall back to a plain collection.
            log.warning("time-series collection not created (using plain): %s", e)

        log.info("Mongo connected (db=%s, transactions=%s)", self._db.name, self.supports_transactions)

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()

    async def ping(self) -> str:
        try:
            await self._client.admin.command("ping")  # type: ignore[union-attr]
            return "ok"
        except Exception as e:  # noqa: BLE001
            return f"down: {e}"

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("MongoStore.connect() not called")
        return self._db

    @property
    def client(self) -> AsyncIOMotorClient:
        if self._client is None:
            raise RuntimeError("MongoStore.connect() not called")
        return self._client

    # -------- Signal audit log -----------------------------------------

    @retry_db()
    async def insert_signals(self, docs: list[dict[str, Any]]) -> list[Any]:
        if not docs:
            return []
        result = await self.db.signals.insert_many(docs, ordered=False)
        return list(result.inserted_ids)

    async def list_signals_for_incident(self, work_item_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
        cursor = (
            self.db.signals.find({"work_item_id": str(work_item_id)})
            .sort("created_at", -1)
            .limit(limit)
        )
        out: list[dict[str, Any]] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            out.append(doc)
        return out

    @retry_db()
    async def link_signals_to_work_item(self, signal_ids: list[Any], work_item_id: UUID) -> int:
        if not signal_ids:
            return 0
        result = await self.db.signals.update_many(
            {"_id": {"$in": signal_ids}},
            {"$set": {"work_item_id": str(work_item_id), "linked_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count

    # -------- Comments --------------------------------------------------

    @retry_db()
    async def insert_comment(self, doc: dict[str, Any]) -> str:
        result = await self.db.comments.insert_one(doc)
        return str(result.inserted_id)

    async def list_comments(self, incident_id: UUID) -> list[dict[str, Any]]:
        cursor = self.db.comments.find({"incident_id": str(incident_id)}).sort("created_at", 1)
        out: list[dict[str, Any]] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            out.append(doc)
        return out

    # -------- Time-series aggregates -----------------------------------

    @retry_db()
    async def insert_signal_metrics(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        try:
            await self.db.signal_metrics.insert_many(rows, ordered=False)
            return len(rows)
        except Exception as e:  # noqa: BLE001
            log.warning("signal_metrics insert failed (non-fatal): %s", e)
            return 0

    async def recent_metrics(self, component_id: str | None = None, minutes: int = 30) -> list[dict[str, Any]]:
        from datetime import timedelta
        match: dict[str, Any] = {"bucket": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=minutes)}}
        if component_id:
            match["meta.component_id"] = component_id
        cursor = self.db.signal_metrics.find(match).sort("bucket", -1).limit(500)
        return [doc async for doc in cursor]
