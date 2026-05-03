"""Rolling throughput counter + periodic console printer.

Single in-process source of truth for `signals_sec`. Workers call `record_*`
and the printer task reads the rolling window every N seconds.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class _Counters:
    received: int = 0
    persisted: int = 0
    rejected_429: int = 0
    debounced: int = 0
    work_items_created: int = 0
    last_per_sec_window: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=60))


_state = _Counters()
_lock = asyncio.Lock()


def record_received(n: int = 1) -> None:
    _state.received += n
    _state.last_per_sec_window.append((time.monotonic(), n))


def record_persisted(n: int = 1) -> None:
    _state.persisted += n


def record_rejected(n: int = 1) -> None:
    _state.rejected_429 += n


def record_debounced(n: int = 1) -> None:
    _state.debounced += n


def record_work_item_created(n: int = 1) -> None:
    _state.work_items_created += n


def signals_per_second(window_seconds: float = 5.0) -> float:
    cutoff = time.monotonic() - window_seconds
    total = sum(n for ts, n in _state.last_per_sec_window if ts >= cutoff)
    return total / window_seconds


def snapshot() -> dict[str, int | float]:
    return {
        "signals_received_total": _state.received,
        "signals_persisted_total": _state.persisted,
        "signals_rejected_429_total": _state.rejected_429,
        "signals_debounced_total": _state.debounced,
        "work_items_created_total": _state.work_items_created,
        "signals_per_sec_5s": round(signals_per_second(5.0), 2),
    }


async def run_printer(interval_seconds: int, queue_depth_fn=None) -> None:
    """Background task: print throughput every `interval_seconds`."""
    while True:
        await asyncio.sleep(interval_seconds)
        snap = snapshot()
        depth = queue_depth_fn() if queue_depth_fn else "?"
        print(
            f"[metrics] signals_sec={snap['signals_per_sec_5s']:>7}  "
            f"queue_depth={depth:>6}  "
            f"received={snap['signals_received_total']}  "
            f"persisted={snap['signals_persisted_total']}  "
            f"rejected_429={snap['signals_rejected_429_total']}  "
            f"work_items={snap['work_items_created_total']}",
            flush=True,
        )
