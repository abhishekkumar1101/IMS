# Prompt 2 — Tech stack decisions

The user explicitly required zero-cost tooling. These choices satisfy that:

| Layer | Choice | Why this, not alternatives |
|---|---|---|
| Backend | Python 3.12 + FastAPI | First-class `asyncio` + simplest path to load `model.pkl` and call `google-generativeai`. Go would beat us on raw throughput but require a Python sidecar for ML. |
| Concurrency | bounded `asyncio.Queue` + `anyio` + `tenacity` retry | Modern primitives without inventing new abstractions. |
| Source of Truth | PostgreSQL 16 | Transactional Work Item + RCA. |
| Time-series | TimescaleDB extension on the same Postgres | One container, two roles. Keeps the diagram + ops simple. |
| Data Lake | MongoDB 7 | Schemaless raw signals; queryable; comments collection. |
| Hot-path | Redis 7 | Streams broker, ZSET debounce, dashboard hash, rate-limit, presence. |
| Frontend | React + Vite + Tailwind + TanStack Query + Zustand | Cleanest professional polish for a dashboard; familiar for reviewers. |
| ML | scikit-learn `IsolationForest` saved with `joblib` | Per the assignment instruction: keep sample small. ~5k synthetic rows train in seconds. |
| AI | Gemini 2.5 Flash Lite via `google-generativeai` | User-supplied key. Free tier covers all dashboard summary calls. |
| Containers | Docker Compose | Required by the spec. |

## Decisions made up front

- **No Kafka**. Redis Streams + bounded `asyncio.Queue` cover the rubric;
  Kafka would balloon footprint with no rubric upside.
- **No auth**. Single-tenant assignment; presence uses anonymous nickname
  generated client-side.
- **No PagerDuty/Slack live integrations**. Alert strategies log + persist
  audit rows — wire-replaceable.
- **Mongo native time-series collections rejected** in favour of TimescaleDB:
  the assignment explicitly enumerates time-series as its own sink, so we
  separate it physically (hypertable) from the Source of Truth tables.
- **State machine in Python, not in DB triggers**. Keeps the rule testable in
  isolation and readable in one file.
