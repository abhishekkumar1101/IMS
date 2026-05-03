"""Sustained load test — proves backpressure (429) kicks in.

Spawn N concurrent workers, each posting batches of M signals as fast as the
backend allows for D seconds. Reports accepted/rejected counts and effective
throughput.

Run:
    python scripts/load_test.py --workers 32 --batch 500 --duration 10
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time
from datetime import datetime, timezone

import httpx

DEFAULT_API = "http://localhost:8000"


def _make_batch(n: int) -> list[dict]:
    component = random.choice(["RDBMS_X", "MCP_Y", "CACHE_Z", "API_GATEWAY", "QUEUE_KAFKA_1"])
    kind = {"RDBMS": "RDBMS_X", "MCP": "MCP_Y", "CACHE": "CACHE_Z", "API": "API_GATEWAY", "QUEUE": "QUEUE_KAFKA_1"}
    return [
        {
            "component_id": component,
            "component_kind": next(k for k, v in kind.items() if v == component),
            "severity": random.choice(["P0", "P1", "P2"]),
            "message": f"synthetic event {random.randint(0, 10**6)}",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": random.uniform(20, 1200),
            "error_rate": random.uniform(0.0, 0.9),
            "payload_size": random.randint(128, 4096),
            "payload": {},
        }
        for _ in range(n)
    ]


async def worker(idx: int, api: str, batch_size: int, deadline: float) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            batch = _make_batch(batch_size)
            try:
                resp = await client.post(f"{api}/signals/batch", json={"signals": batch}, timeout=5.0)
                data = resp.json()
                accepted += int(data.get("accepted", 0))
                if resp.status_code == 429:
                    rejected += len(batch) - int(data.get("accepted", 0))
            except Exception:
                rejected += len(batch)
    return accepted, rejected


async def main(args) -> None:
    deadline = time.monotonic() + args.duration
    tasks = [worker(i, args.api, args.batch, deadline) for i in range(args.workers)]
    results = await asyncio.gather(*tasks)
    accepted = sum(a for a, _ in results)
    rejected = sum(r for _, r in results)
    total = accepted + rejected
    print(f"workers={args.workers} batch={args.batch} duration={args.duration}s")
    print(f"  accepted={accepted:,}  rejected_429={rejected:,}  total={total:,}")
    print(f"  effective_throughput={accepted / args.duration:,.0f} signals/sec")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--batch", type=int, default=500)
    p.add_argument("--duration", type=float, default=10.0)
    asyncio.run(main(p.parse_args()))
