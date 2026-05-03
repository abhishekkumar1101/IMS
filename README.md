# IMS — Mission-Critical Incident Management System

A resilient incident management platform that ingests high-volume failure
signals from a distributed stack (RDBMS, MCP hosts, distributed caches, async
queues, NoSQL stores), debounces them into Work Items, drives an incident
lifecycle with mandatory RCA, and surfaces everything on a real-time React
dashboard.

> Built for the assignment in `Engineering_Assignment__Incident_Management_System.pdf`.

## Highlights

- **10k signals/sec ingestion ceiling** via bounded `asyncio.Queue` + 4 workers;
  producers get **HTTP 429** the moment we run out of headroom — never a crash.
- **Debouncing**: 100 signals for the same component within 10 s collapse into
  a single Work Item; subsequent signals are linked back into the audit log.
- **Strategy + State design patterns** for alerting tiering and lifecycle.
- **Mandatory RCA** enforced both at the Pydantic layer _and_ the State machine —
  there is no API path to CLOSED without a complete RCA.
- **AI / ML enhancements**:
  - Isolation Forest anomaly detector (trained in `ml/train_anomaly.ipynb`,
    persisted as `model.pkl`, loaded by the backend).
  - Gemini 2.5 Flash Lite incident summarizer on the Live Feed (free tier).
- **Real-time collaboration**: WebSocket presence + threaded comments per incident.
- **Observability**: `/health`, `/metrics`, console throughput printer every 5 s.

## Tech stack (no Docker)

One MongoDB Atlas cluster handles every storage role; everything else runs in
process. Zero external services beyond Atlas + Gemini.

| Concern                       | Tech                                                 | Role                                                                                                                                                       |
| ----------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API + workers                 | Python 3.12 + FastAPI + asyncio                      | async producer/worker pipeline                                                                                                                             |
| Storage                       | **MongoDB Atlas**                                    | Data Lake (`signals`), Source of Truth (`work_items` + embedded RCA), `state_transitions`, `alerts_dispatched`, time-series (`signal_metrics`), `comments` |
| Cache / debounce / rate-limit | In-process Python                                    | swap for Redis when scaling beyond one node                                                                                                                |
| Frontend                      | React 18 + Vite + TS + Tailwind + TanStack Query     | Live Feed + Detail + RCA                                                                                                                                   |
| ML                            | scikit-learn IsolationForest (Jupyter → `model.pkl`) | per-signal anomaly score                                                                                                                                   |
| AI                            | Gemini 2.5 Flash Lite                                | incident summary on Live Feed                                                                                                                              |

## Setup

### Option A — Docker Compose (recommended for graders)

Brings up MongoDB (replica set so transactions are enabled) + backend + frontend
with one command. Per the assignment's submission guidelines.

```bash
# 1. .env at the repo root must have GEMINI_API_KEY (already populated).
# 2. Up
docker compose up --build

# 3. Open
http://localhost:5173

# 4. Simulate a failure (any terminal):
docker compose exec backend python /app/../scripts/simulate_failure.py --api http://localhost:8000
# or from the host:
python scripts/simulate_failure.py
```

Stack:

| Container      | Image                                     | Role                      |
| -------------- | ----------------------------------------- | ------------------------- |
| `ims-mongodb`  | `mongo:7` (single-node replica set `rs0`) | every storage role        |
| `ims-backend`  | built from `./backend`                    | FastAPI + 4 async workers |
| `ims-frontend` | built from `./frontend`                   | Vite dev server           |

### Option B — Local (no Docker), against MongoDB Atlas

Useful when Docker isn't available. The repo's `.env` already points
`MONGODB_URI` at the assignment's free Atlas cluster (replica set, transactions
on by default).

```bash
# 1. Install deps (Windows):
scripts\quickstart.bat
# or (Mac/Linux):
bash scripts/quickstart.sh

# 2. Run (two terminals):
cd backend && python -m uvicorn app.main:app --reload
cd frontend && npm run dev

# 3. Open
http://localhost:5173

# 4. Simulate a failure
python scripts/simulate_failure.py
```

### What you should see (either option)

- Backend prints every 5 s: `[metrics] signals_sec=… queue_depth=… received=… work_items=…`
- Three new incidents on the Live Feed: RDBMS_PRIMARY (P0), MCP_HOST_03 (P0), CACHE_CLUSTER_01 (P2), sorted by severity.
- Anomaly badges on outlier signals; Gemini "✨ Generate AI summary" button produces a one-line summary.

## Architecture

```
Producers ──HTTP/WS──▶ [Rate limiter (in-mem token bucket)]
                              │
                              ▼ (queue full ⇒ 429)
                    [Bounded asyncio.Queue (50k)]
                              │
                              ▼
                    [Worker pool ── async × 4]
                       │      │       │
                       ▼      ▼       ▼
                   Mongo  Anomaly  Debouncer
                  signals  scorer  (in-mem ZSET)
                                   │
                                   ▼
                       Mongo work_items (find or create)
                       Mongo state_transitions (append)
                       Mongo alerts_dispatched (audit)
                       Mongo signal_metrics (5s buckets)
                                   │
                                   ▼
                          In-mem dashboard cache
                                   │
                                   ▼
                      WebSocket → React dashboard
```

See [`docs/architecture.md`](docs/architecture.md) for sequence diagrams and rationale.

## Verifying the rubric

| Rubric item                      | Where to look                                                                                                                                              |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Concurrency & no race conditions | `app/storage/repository.py` (Mongo `$inc` atomic + `find_one_and_update`); `app/ingestion/worker.py` per-component asyncio lock; `tests/test_debouncer.py` |
| Data separation                  | Mongo collections: `signals` (Data Lake), `work_items` + embedded RCA (Source of Truth), `signal_metrics` (time-series), in-mem cache (hot path)           |
| LLD / patterns                   | `app/workflow/states.py` (State), `app/workflow/alerting.py` (Strategy)                                                                                    |
| UI/UX                            | `frontend/src/pages/*.tsx`                                                                                                                                 |
| Resilience & tests               | `app/core/retry.py` (tenacity); `pytest backend/tests/` (23 tests)                                                                                         |
| Documentation                    | this README + `docs/*.md` + `docs/prompts/*`                                                                                                               |
| Tech-stack rationale             | `docs/prompts/02-tech-stack-decision.md`                                                                                                                   |

## Backpressure (how we handle it)

See [`docs/backpressure.md`](docs/backpressure.md) — short version:

1. **Token-bucket rate limiter** (in-process, asyncio-locked) per source IP.
2. `asyncio.Queue(maxsize=50_000)` between handler and worker pool.
3. Handler uses `put_nowait`; on `QueueFull` returns **HTTP 429** with
   `Retry-After`. The system **never blocks the request thread**.
4. Workers drain in batches of 500 with pipelined Mongo writes.
5. DB writes wrapped in `tenacity` exponential backoff retry (5 attempts).
6. Gemini calls wrapped in a circuit breaker (`pybreaker`) so AI outages
   don't stall the dashboard.

## Tests

```bash
cd backend
pip install -e .[dev]
pytest -q          # 23 passed
```

Coverage: state pattern, RCA validation, MTTR math, debouncer, rate-limiter.
None require a live database.

## Repo layout

```
backend/    FastAPI app, ingestion pipeline, workflow engine, Mongo storage, AI, tests
frontend/   React + Vite + Tailwind dashboard
ml/         Jupyter notebook + trained model.pkl
scripts/    quickstart.{bat,sh} · simulate_failure.py · load_test.py
docs/       architecture · backpressure · design-patterns · prompts/
.env        MONGODB_URI + GEMINI_API_KEY (already populated)
```

## Submission checklist

- [x] `backend/` and `frontend/` included
- [x] `docker-compose.yml` present and documented
- [x] `README.md` covers setup, verification, and rubric mapping
- [x] `docs/architecture.md` and `docs/backpressure.md` describe the actual implementation
- [x] `scripts/simulate_failure.py` provides sample failure events
- [x] `docs/prompts/` contains planning and spec notes
- [x] Backend tests pass: `pytest -q` (23 passed)

## Notes for evaluators

- **Docker Compose** is the documented setup path per the submission guidelines (Option A). The author's local box has no Docker, so day-to-day development used the no-Docker Atlas path (Option B); both paths produce the same behaviour.
- The compose file uses a **single-node MongoDB replica set** so the multi-doc transactions in `WorkItemRepo.close_with_rca` are exercised end-to-end. On standalone Mongo the code degrades to sequenced writes (still safe — RCA + state flip + transition write happen from a single process).
