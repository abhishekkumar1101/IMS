"""IMS — FastAPI entrypoint (MongoDB-only build).

Single MongoDB cluster (Atlas / local / replica set) acts as:
  - Data Lake          (`signals`)
  - Source of Truth    (`work_items` + embedded `rca`, `state_transitions`)
  - Time-series sink   (`signal_metrics`)
  - Comments           (`comments`)
  - Audit              (`alerts_dispatched`)

Hot-path cache, rate-limiter, debouncer, presence and pub/sub all run in
process — appropriate for the assignment's single-node deployment. Each
in-memory module documents how to swap to a distributed store later.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import comments as comments_router
from app.api import incidents as incidents_router
from app.api import ingest as ingest_router
from app.api import rca as rca_router
from app.api import ws as ws_router
from app.ai.anomaly import AnomalyScorer
from app.ai.gemini_summarizer import GeminiSummarizer
from app.collab.hub import DashboardHub, IncidentHub
from app.collab.presence import PresenceRegistry
from app.core import metrics
from app.core.config import get_settings
from app.core.ratelimit import InMemoryTokenBucket
from app.ingestion.debouncer import Debouncer
from app.ingestion.queue import IngestQueue
from app.ingestion.worker import IngestionWorkerPool
from app.models.schemas import HealthOut
from app.storage.cache import InMemoryCache
from app.storage.mongo import MongoStore
from app.workflow.alerting import AlertDispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("ims.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info(
        "Booting IMS backend (gemini_model=%s, mongo_uri=%s)",
        settings.gemini_model,
        _redact(settings.effective_mongo_uri),
    )

    # --- Storage ---------------------------------------------------------
    mongo = MongoStore(settings.effective_mongo_uri, settings.effective_db_name)
    await mongo.connect()

    cache = InMemoryCache()

    # --- Domain services -------------------------------------------------
    rate_limiter = InMemoryTokenBucket(
        capacity=settings.ingest_rate_limit_per_sec,
        refill_per_sec=settings.ingest_rate_limit_per_sec,
    )

    anomaly = AnomalyScorer(settings.anomaly_model_path, settings.anomaly_score_threshold)
    anomaly.load()  # non-fatal

    summarizer = GeminiSummarizer(api_key=settings.gemini_api_key, model=settings.gemini_model)

    debouncer = Debouncer(
        window_seconds=settings.debounce_window_seconds,
        threshold=settings.debounce_signal_threshold,
    )

    alerter = AlertDispatcher(mongo=mongo)
    presence = PresenceRegistry()
    incident_hub = IncidentHub()
    dashboard_hub = DashboardHub()

    queue = IngestQueue(maxsize=settings.queue_max_size)

    workers = IngestionWorkerPool(
        queue=queue,
        mongo=mongo,
        cache=cache,
        debouncer=debouncer,
        anomaly=anomaly,
        alerter=alerter,
        worker_count=settings.worker_count,
        batch_size=settings.worker_batch_size,
    )
    await workers.start()

    app.state.settings = settings
    app.state.mongo = mongo
    app.state.cache = cache
    app.state.queue = queue
    app.state.workers = workers
    app.state.rate_limiter = rate_limiter
    app.state.debouncer = debouncer
    app.state.anomaly = anomaly
    app.state.summarizer = summarizer
    app.state.presence = presence
    app.state.alerter = alerter
    app.state.incident_hub = incident_hub
    app.state.dashboard_hub = dashboard_hub

    printer_task = asyncio.create_task(
        metrics.run_printer(settings.metrics_print_interval_seconds, queue_depth_fn=queue.size)
    )

    log.info("IMS backend ready on http://0.0.0.0:8000")
    try:
        yield
    finally:
        log.info("Shutting down...")
        printer_task.cancel()
        await workers.stop()
        await mongo.close()


def _redact(uri: str) -> str:
    """Mask credentials in a Mongo URI for logging."""
    import re

    return re.sub(r"://[^@]+@", "://***@", uri)


def create_app() -> FastAPI:
    app = FastAPI(title="IMS — Incident Management System", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthOut)
    async def health() -> HealthOut:
        deps = {
            "mongo": await app.state.mongo.ping(),
            "anomaly_model": "loaded" if app.state.anomaly.is_ready else "missing",
            "gemini": "configured" if app.state.summarizer.is_configured else "disabled",
            "transactions": "supported" if app.state.mongo.supports_transactions else "single-node",
        }
        ok = deps["mongo"] == "ok"
        return HealthOut(status="ok" if ok else "degraded", deps=deps, metrics=metrics.snapshot())

    @app.get("/metrics")
    async def metrics_endpoint() -> dict:
        snap = metrics.snapshot()
        snap["queue_depth"] = app.state.queue.size()
        return snap

    app.include_router(ingest_router.router)
    app.include_router(incidents_router.router)
    app.include_router(rca_router.router)
    app.include_router(comments_router.router)
    app.include_router(ws_router.router)
    return app


app = create_app()
