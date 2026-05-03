# Prompt 3 — Implementation execution log

Full plan lives at `~/.claude/plans/for-u-have-to-quiet-floyd.md` (also
mirrored below for the submission). It was approved before any code was
written.

## Build order (matched the task list)

1. `docker-compose.yml`, `.env.example`, `.gitignore`, schema migration
   `backend/migrations/init.sql` (creates the hypertable + continuous
   aggregate).
2. Backend skeleton — `pyproject.toml`, `Dockerfile`, `app/main.py` lifespan,
   `app/core/{config,metrics,retry,ratelimit}.py`, `app/models/schemas.py`.
3. Storage clients — `app/storage/{postgres,mongo,redis,timescale,repository}.py`.
4. Workflow engine — `app/workflow/{states,alerting,transitions,mttr}.py`.
5. Anomaly model — `ml/train_anomaly.ipynb` executed to produce `ml/model.pkl`.
6. AI integration — `app/ai/{anomaly,gemini_summarizer}.py`.
7. Ingestion pipeline — `app/ingestion/{queue,debouncer,worker}.py`.
8. Collab — `app/collab/{presence,hub}.py`.
9. API routes — `app/api/{ingest,incidents,rca,comments,ws}.py`.
10. Tests — `backend/tests/test_*.py` (23 passing, no live DB needed).
11. Frontend — Vite + React + Tailwind app under `frontend/`.
12. Scripts — `scripts/{simulate_failure,load_test}.py`.
13. Docs — this folder + the README.

## Key invariants enforced more than once

| Invariant | Enforcement layers |
|---|---|
| RCA required to close | Pydantic length checks → Pydantic cross-field validator (end > start) → State pattern in `ResolvedState.close` → SQL `SELECT FOR UPDATE; INSERT rcas; UPDATE work_items` in one tx |
| One Work Item per component per window | Redis `SETNX wi-lock:{cid}` with TTL (debouncer) → Postgres `pg_advisory_xact_lock(hashtext(cid))` (repository.create) |
| Backpressure never blocks request | `put_nowait` only → `IngestQueueFull` → 429 |

## How to reproduce the train + run

```bash
# Train ML model
cd ml
python -c "import joblib, numpy as np, pandas as pd; from sklearn.ensemble import IsolationForest; ..."  # see ml/README.md
# (or open train_anomaly.ipynb and run all cells)

# Stack
docker compose up --build
python scripts/simulate_failure.py
```

## Plan file (verbatim summary)

The plan that was approved before the build:

- Tech stack: Python+FastAPI / Postgres+Timescale / MongoDB / Redis / React+Vite+Tailwind / IsolationForest+pkl / Gemini 2.5 Flash Lite.
- Repo layout: `/backend`, `/frontend`, `/ml`, `/scripts`, `/docs`.
- Patterns: State (`workflow/states.py`) + Strategy (`workflow/alerting.py`).
- Backpressure stack: rate limiter → bounded queue → batched workers → retry → circuit breaker.
- Verification matrix in the plan file lists 10 end-to-end checks.

The plan was kept faithful end to end; only ratelimit / debouncer test details
required iteration (use `eval` instead of `script_load` for `fakeredis`
compatibility; use a unique counter for ZSET members so duplicate scores
within a millisecond don't collapse).
