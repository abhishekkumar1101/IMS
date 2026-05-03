"""Ingestion worker pool — drains the bounded queue.

Per batch:
1. Score signals (Anomaly model).
2. Insert into Mongo `signals` (raw audit log / Data Lake).
3. Debounce per-component → maybe create Work Item (Mongo Source of Truth).
4. Link signal_ids → Work Item.
5. Increment counts on the WI; aggregate into the time-series collection.
6. Push a snapshot onto the in-memory dashboard cache.
7. Trigger alert dispatch (Strategy pattern) for newly created WIs.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.ai.anomaly import AnomalyScorer
from app.core import metrics
from app.ingestion.debouncer import Debouncer
from app.ingestion.queue import IngestQueue
from app.models.schemas import ComponentKind, Severity
from app.storage.cache import InMemoryCache
from app.storage.mongo import MongoStore
from app.storage.repository import WorkItemRepo
from app.workflow.alerting import AlertDispatcher, severity_for

log = logging.getLogger("ims.worker")


def _bucket_5s(ts: datetime) -> datetime:
    ts = ts.astimezone(timezone.utc)
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % 5), tz=timezone.utc)


class IngestionWorkerPool:
    def __init__(
        self,
        *,
        queue: IngestQueue,
        mongo: MongoStore,
        cache: InMemoryCache,
        debouncer: Debouncer,
        anomaly: AnomalyScorer,
        alerter: AlertDispatcher,
        worker_count: int,
        batch_size: int,
    ) -> None:
        self.queue = queue
        self.mongo = mongo
        self.cache = cache
        self.debouncer = debouncer
        self.anomaly = anomaly
        self.alerter = alerter
        self.worker_count = worker_count
        self.batch_size = batch_size
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()
        self.repo = WorkItemRepo(mongo)
        # Per-component lock — serializes "find or create WI" across worker tasks.
        # Without this, two workers can both observe `find_open == None` and one will
        # silently drop its signal-count increment because the WI is racing.
        self._component_locks: dict[str, asyncio.Lock] = {}
        self._component_locks_guard = asyncio.Lock()

    async def _component_lock(self, cid: str) -> asyncio.Lock:
        async with self._component_locks_guard:
            lock = self._component_locks.get(cid)
            if lock is None:
                lock = asyncio.Lock()
                self._component_locks[cid] = lock
            return lock

    async def start(self) -> None:
        for i in range(self.worker_count):
            t = asyncio.create_task(self._run(i), name=f"ingest-worker-{i}")
            self._tasks.append(t)

    async def stop(self) -> None:
        self._stopping.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run(self, worker_id: int) -> None:
        log.info("worker %d started", worker_id)
        while not self._stopping.is_set():
            try:
                batch = await self.queue.get()
                try:
                    await self._process(batch)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("worker %d: batch failed", worker_id)
        log.info("worker %d stopped", worker_id)

    async def _process(self, batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        now = datetime.now(timezone.utc)
        for s in batch:
            s.setdefault("created_at", now)
            if isinstance(s["created_at"], str):
                s["created_at"] = datetime.fromisoformat(s["created_at"])

        # 1. Debounce — also gives us per-component frequencies for the model.
        debounce = await self.debouncer.observe_batch(s["component_id"] for s in batch)
        freq_lookup = {cid: r.freq_in_window for cid, r in debounce.items()}

        # 2. Anomaly score (in-place mutate).
        self.anomaly.score_batch(batch, freq_lookup)

        # 3. Persist raw signals to Mongo (Data Lake).
        docs: list[dict[str, Any]] = []
        for s in batch:
            doc = {**s, "_status": "raw"}
            doc["component_kind"] = (
                s["component_kind"].value if hasattr(s["component_kind"], "value") else s["component_kind"]
            )
            doc["severity"] = s["severity"].value if hasattr(s["severity"], "value") else s["severity"]
            docs.append(doc)
        try:
            inserted_ids = await self.mongo.insert_signals(docs)
            for doc, _id in zip(batch, inserted_ids):
                doc["mongo_id"] = _id
            metrics.record_persisted(len(batch))
        except Exception:
            log.exception("signals insert failed — dropping batch")
            return

        # 4. Group by component for WI creation/linking.
        by_component: dict[str, list[dict[str, Any]]] = {}
        for s in batch:
            by_component.setdefault(s["component_id"], []).append(s)

        wi_ids_for_alert: list[tuple[str, str, Severity]] = []

        for cid, sigs in by_component.items():
            lock = await self._component_lock(cid)
            async with lock:
                existing = await self.repo.find_open_for_component(cid)
                wi: dict | None = existing
                if wi is None:
                    # No open WI exists — either we hold the debounce lock (this is the
                    # first burst), or we're an out-of-order batch arriving before the
                    # first burst's WI committed. Either way we must own creation here.
                    first = min(sigs, key=lambda x: x["created_at"])
                    kind = first["component_kind"]
                    kind_e = ComponentKind(kind) if not isinstance(kind, ComponentKind) else kind
                    sev_in = first["severity"]
                    sev_e = Severity(sev_in) if not isinstance(sev_in, Severity) else sev_in
                    effective_sev = severity_for(kind_e, sev_e)
                    wi = await self.repo.create(
                        component_id=cid,
                        component_kind=kind_e,
                        severity=effective_sev,
                        title=f"{kind_e.value} failure on {cid}",
                        first_signal_at=first["created_at"],
                    )
                    # Only count as "created by this batch" when the in-DB record was new
                    # (the repo dedupes via the (component, OPEN/INVESTIGATING) filter).
                    if int(wi.get("signal_count", 0)) == 0:
                        metrics.record_work_item_created()
                        wi_ids_for_alert.append((wi["id"], cid, effective_sev))

            if wi is not None:
                wi_id = wi["id"]
                last_ts = max(s["created_at"] for s in sigs)
                await self.repo.increment_signal_counts(UUID(wi_id) if isinstance(wi_id, str) else wi_id, len(sigs), last_ts)
                ids = [s["mongo_id"] for s in sigs if "mongo_id" in s]
                if ids:
                    await self.mongo.link_signals_to_work_item(ids, UUID(wi_id) if isinstance(wi_id, str) else wi_id)
                metrics.record_debounced(len(sigs) - 1)

                # In-memory dashboard hot-path cache.
                await self.cache.upsert_dashboard_incident(
                    str(wi_id),
                    json.dumps(
                        {
                            "id": str(wi_id),
                            "component_id": cid,
                            "severity": str(wi["severity"]),
                            "state": str(wi["state"]),
                            "signal_count": int(wi.get("signal_count", 0)) + len(sigs),
                            "last_signal_at": last_ts.isoformat(),
                        },
                        default=str,
                    ),
                )

        # 5. Time-series aggregate (Mongo time-series collection).
        agg: dict[tuple[datetime, str, str], list[int]] = defaultdict(lambda: [0, 0])
        for s in batch:
            key = (
                _bucket_5s(s["created_at"]),
                s["component_id"],
                s["severity"].value if hasattr(s["severity"], "value") else s["severity"],
            )
            agg[key][0] += 1
            if s.get("is_anomalous"):
                agg[key][1] += 1
        if agg:
            rows = [
                {
                    "bucket": k[0],
                    "meta": {"component_id": k[1], "severity": k[2]},
                    "signal_count": v[0],
                    "anomaly_count": v[1],
                }
                for k, v in agg.items()
            ]
            await self.mongo.insert_signal_metrics(rows)

        # 6. Alerts for newly created WIs.
        for wi_id, cid, sev in wi_ids_for_alert:
            await self.alerter.dispatch(
                work_item_id=str(wi_id),
                severity=sev,
                component_id=cid,
                message=f"New {sev.value} incident on {cid}",
            )
