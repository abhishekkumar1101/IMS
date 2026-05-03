"""Simulate a cross-stack failure event.

Sequence:
1. ~5,000 RDBMS_PRIMARY signals over ~2s    → P0 (debounces to 1 work item)
2. brief pause
3. ~3,000 MCP_HOST_03 signals over ~1.5s    → P0 (1 more WI)
4. background trickle of CACHE_CLUSTER_01 P2 signals (300)

Run:
    python scripts/simulate_failure.py [--api http://localhost:8000]
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time
from datetime import datetime, timezone

import httpx

DEFAULT_API = "http://localhost:8000"

RDBMS_MESSAGES = [
    "connection refused on primary replica",
    "lock_timeout exceeded for write transaction",
    "vacuum process consumed all autovacuum workers",
    "checkpoint write took 14s — IO saturated",
    "replication lag > 30s on standby",
]
MCP_MESSAGES = [
    "tool call timeout (15s) on host MCP_HOST_03",
    "context window OOM during sync",
    "model invocation rate-limited upstream",
    "failed to negotiate handshake with downstream MCP",
]
CACHE_MESSAGES = [
    "evicted 12% of keys due to maxmemory pressure",
    "cluster reshard in progress",
    "slowlog spike: GET p99 = 240ms",
]


def _signal(component_id: str, kind: str, severity: str, msg: str) -> dict:
    return {
        "component_id": component_id,
        "component_kind": kind,
        "severity": severity,
        "message": msg,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": random.uniform(50, 1500),
        "error_rate": random.uniform(0.01, 0.95),
        "payload_size": random.randint(256, 4096),
        "payload": {"trace_id": f"trace-{random.randint(1, 10**6)}"},
    }


async def burst(
    client: httpx.AsyncClient,
    *,
    api: str,
    component_id: str,
    kind: str,
    severity: str,
    messages: list[str],
    n: int,
    duration_s: float,
    batch_size: int = 200,
) -> tuple[int, int, int]:
    sent = 0
    accepted_total = 0
    rejected_total = 0
    rate = max(1, n // batch_size)
    sleep_per_batch = duration_s / rate
    for _ in range(rate):
        batch = [
            _signal(component_id, kind, severity, random.choice(messages))
            for _ in range(min(batch_size, n - sent))
        ]
        if not batch:
            break
        try:
            resp = await client.post(f"{api}/signals/batch", json={"signals": batch}, timeout=10.0)
            data = resp.json()
            accepted_total += int(data.get("accepted", 0))
            if resp.status_code == 429:
                rejected_total += len(batch) - int(data.get("accepted", 0))
        except Exception as e:  # noqa: BLE001
            print(f"  ! batch failed: {e}")
            rejected_total += len(batch)
        sent += len(batch)
        await asyncio.sleep(sleep_per_batch)
    return sent, accepted_total, rejected_total


async def main(api: str) -> None:
    print(f"-> targeting {api}")
    async with httpx.AsyncClient() as client:
        # Health
        try:
            h = await client.get(f"{api}/health", timeout=5.0)
            print(f"  health: {h.status_code} {h.json().get('status')}")
        except Exception as e:
            print(f"  ! cannot reach API: {e}")
            return

        t0 = time.monotonic()

        print("\n[1/3] RDBMS_PRIMARY: 5000 signals / 2s")
        s1 = await burst(client, api=api, component_id="RDBMS_PRIMARY", kind="RDBMS",
                         severity="P0", messages=RDBMS_MESSAGES, n=5000, duration_s=2.0)
        print(f"     sent={s1[0]} accepted={s1[1]} rejected={s1[2]}")

        await asyncio.sleep(0.4)

        print("\n[2/3] MCP_HOST_03: 3000 signals / 1.5s")
        s2 = await burst(client, api=api, component_id="MCP_HOST_03", kind="MCP",
                         severity="P0", messages=MCP_MESSAGES, n=3000, duration_s=1.5)
        print(f"     sent={s2[0]} accepted={s2[1]} rejected={s2[2]}")

        await asyncio.sleep(0.3)

        print("\n[3/3] CACHE_CLUSTER_01: 300 signals / 3s")
        s3 = await burst(client, api=api, component_id="CACHE_CLUSTER_01", kind="CACHE",
                         severity="P2", messages=CACHE_MESSAGES, n=300, duration_s=3.0)
        print(f"     sent={s3[0]} accepted={s3[1]} rejected={s3[2]}")

        elapsed = time.monotonic() - t0
        total_sent = s1[0] + s2[0] + s3[0]
        total_accepted = s1[1] + s2[1] + s3[1]
        total_rejected = s1[2] + s2[2] + s3[2]
        print(
            f"\n=> total sent={total_sent} accepted={total_accepted} rejected={total_rejected} "
            f"in {elapsed:.2f}s  ({total_sent/elapsed:,.0f} signals/sec)"
        )
        print("=> open http://localhost:5173 to see the dashboard")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--api", default=DEFAULT_API)
    args = p.parse_args()
    asyncio.run(main(args.api))
