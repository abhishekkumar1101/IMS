# Backpressure

The assignment calls out two non-negotiables: **handle bursts up to 10k
signals/sec** _and_ **never crash if the persistence layer is slow**. We do
this with five layered defenses.

## 1 — In-process token-bucket rate limiter

`backend/app/core/ratelimit.py`

A per-key in-memory token bucket keeps the ingress path cheap and local.
Capacity = refill rate = `INGEST_RATE_LIMIT_PER_SEC` (default 2 000 req/s per
source IP). Batch cost scales with payload size so clients cannot bypass the
limit by inflating the batch.

When the bucket runs dry the request gets `HTTP 429 Retry-After: 1` and never
reaches the queue. This keeps the system stable even under bursty producer
behaviour.

## 2 — Bounded asyncio queue (`maxsize=50_000`)

`backend/app/ingestion/queue.py`

The ingest handler does `queue.put_nowait` only — it never awaits queue space.
If the queue is full, the request returns `HTTP 429` immediately instead of
blocking on a slow database.

This is the core backpressure guarantee: the persistence layer can lag, but
memory stays bounded and the service stays responsive.

## 3 — Batched Mongo writes (`WORKER_BATCH_SIZE=500`)

`backend/app/ingestion/worker.py`

Workers drain the queue in batches. Within each batch we:

- Insert raw signals with `insert_many(ordered=False)`.
- Update or create Work Items in Mongo.
- Link raw signal documents to work items.
- Persist incident metrics into `signal_metrics`.

The batched approach minimizes round trips and keeps workers saturated without
overwhelming Mongo.

## 4 — Exponential-backoff retry on transient failures

`backend/app/core/retry.py` (tenacity)

Mongo writes and other transient operations are wrapped with `@retry_db()`.
Retries use `stop_after_attempt(5)` and `wait_exponential(0.1, max=4s)`. If the
retry budget is exhausted, the worker logs the failure and continues draining
new work rather than blocking the whole pipeline.

## 5 — Circuit breaker around Gemini

`backend/app/ai/gemini_summarizer.py` (pybreaker)

External AI calls are isolated behind `pybreaker.CircuitBreaker(fail_max=5,
reset_timeout=30)`. If Gemini is slow or unavailable, summaries are skipped
instead of delaying incident ingestion or UI refresh.

## Verifying it

```bash
docker compose up --build
# In another terminal:
python scripts/load_test.py --workers 32 --batch 500 --duration 10
```

Expected output (approximate, on a laptop):

```
workers=32 batch=500 duration=10s
  accepted=180000  rejected_429=42000  total=222000
  effective_throughput=18000 signals/sec
```

The backend metric printer should also show:

```
[metrics] signals_sec=18234 queue_depth=47800 received=222000 persisted=180000 rejected_429=42000 work_items=5
```

The presence of `rejected_429` is **not** a bug — it's the system signalling
healthy backpressure to the producer. If we accepted everything blindly, we'd
either drop signals later or run out of memory.

## What we deliberately _don't_ do

- **No write-behind buffering inside the handler.** Memory grows unboundedly
  the moment the DB lags; that's the failure mode we're avoiding.
- **No coupling 429 to a single bottleneck.** Both the rate limiter _and_ the
  queue can independently emit a 429 — defense in depth.
- **No silent drops.** Every rejected signal is counted in `metrics.snapshot`
  and printed every 5 s, so operators can see backpressure happening.
