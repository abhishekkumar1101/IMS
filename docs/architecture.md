# Architecture

## Implementation overview

This repo implements a MongoDB-first, single-process IMS.
MongoDB acts as the durable store for every persistence concern:

- Data Lake: raw `signals`
- Source of Truth: `work_items`, `rca`, `state_transitions`
- Time-series sink: `signal_metrics`
- Comments + audit: `comments`, `alerts_dispatched`

The hot path is implemented in-process using `asyncio`, which keeps the
single-node Docker Compose setup simple and self-contained. Each in-memory
component includes a documented swap point for Redis/Postgres if the system
is later scaled out.

## High-level data flow

```mermaid
flowchart LR
    P[Producers<br/>APIs · MCP · Cache · Queue · NoSQL]
    P -- HTTP/WS JSON --> RL[Rate limiter<br/>In-memory token bucket]
    RL --> Q[(Bounded asyncio.Queue<br/>maxsize=50k)]
    Q --> W[Worker pool<br/>asyncio]
    W --> M[(MongoDB<br/>raw signals)]
    W --> B{Debouncer<br/>in-process window}
    B -- first burst in window --> WI[(Work Item create/update)]
    W --> A[Anomaly scorer<br/>model.pkl]
    W --> C[(In-memory dashboard cache)]
    WI --> AL[Alert dispatcher<br/>Strategy pattern]
    C -- WS push --> UI[React dashboard]
    P -. Gemini summary .-> UI
    UI -- WS --> COL[Presence + Comments hub]
```

## Component responsibilities

| Component             | File                                           | Role                                                                         |
| --------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------- |
| **Ingest router**     | `backend/app/api/ingest.py`                    | Validates payload; rate-limits; enqueues; returns 202/429                    |
| **Bounded queue**     | `backend/app/ingestion/queue.py`               | Decouples handler from worker; `put_nowait` only                             |
| **Worker pool**       | `backend/app/ingestion/worker.py`              | Drains queue; orchestrates Mongo writes, debouncing, analytics, and alerts   |
| **Debouncer**         | `backend/app/ingestion/debouncer.py`           | In-process window per component; collapses bursty signals into one Work Item |
| **Anomaly scorer**    | `backend/app/ai/anomaly.py`                    | Lazy-loaded `model.pkl`; marks signal outliers                               |
| **Workflow engine**   | `backend/app/workflow/{states,transitions}.py` | State pattern + transition validation                                        |
| **Alert dispatcher**  | `backend/app/workflow/alerting.py`             | Strategy pattern — severity-specific alerting                                |
| **Cache**             | `backend/app/storage/cache.py`                 | In-memory dashboard state + summary cache                                    |
| **Storage**           | `backend/app/storage/mongo.py`                 | MongoDB stores raw signals + Work Items + metrics + comments                 |
| **Gemini summarizer** | `backend/app/ai/gemini_summarizer.py`          | `gemini-2.5-flash-lite` + circuit breaker + TTL cache                        |
| **WS hubs**           | `backend/app/collab/hub.py`, `app/api/ws.py`   | Live feed + per-incident presence/comments                                   |

## Why this stack

- **FastAPI + asyncio** — single language for HTTP, worker pipeline, ML model loading, and WebSockets.
- **MongoDB** for durability across every sink: audit log, incident source of truth, time-series, comments, and alerts.
- **In-process hot path** for rate limiting, debouncing, caching, and presence — ideal for one-node Docker Compose.
- **React + Vite + Tailwind** — fast frontend iteration with responsive incident dashboard and RCA flow.
- **scikit-learn IsolationForest** — lightweight anomaly scoring for raw signal anomalies.
- **Gemini 2.5 Flash Lite** — free-tier AI summaries without blocking the core pipeline.

## Sequence: a signal lands

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI ingest
    participant RL as In-memory bucket
    participant Q as asyncio.Queue
    participant W as Worker
    participant M as MongoDB
    participant D as Debouncer
    participant UI as Dashboard

    C->>API: POST /signals/batch
    API->>RL: consume tokens
    RL-->>API: allowed
    API->>Q: put_nowait(batch)
    API-->>C: 202 accepted

    loop async
      W->>Q: get()
      W->>D: observe(component_ids)
      W->>M: insert raw signals
      D-->>W: should_create_wi?
      alt new WI
        W->>M: create Work Item + alert + metrics
      else existing WI
        W->>M: update Work Item, link signals, increment counters
      end
      W->>M: upsert dashboard snapshot
      W->>UI: push updated incident state via WS
    end
```

## Sequence: closing with RCA

```mermaid
sequenceDiagram
    participant UI as Dashboard
    participant API as FastAPI rca
    participant SM as State machine
    participant M as MongoDB

    UI->>API: POST /incidents/{id}/rca
    API->>SM: ResolvedState.close(ctx)
    Note over SM: validates RCA fields,<br/>raises IllegalTransition if missing
    SM-->>API: ok
    API->>M: transaction begins
    API->>M: insert RCA
    API->>M: update Work Item state + mttr
    API->>M: insert state transition audit
    API->>M: commit
    API-->>UI: 200 WorkItemOut (state=CLOSED)
```
