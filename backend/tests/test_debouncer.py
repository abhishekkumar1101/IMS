"""Debouncer logic — pure in-memory, no Redis required."""
from __future__ import annotations

import asyncio

import pytest

from app.ingestion.debouncer import Debouncer


async def test_first_burst_creates_one_work_item():
    deb = Debouncer(window_seconds=10, threshold=100)
    create_flags = []
    freqs = []
    for _ in range(5):
        out = await deb.observe_batch(["RDBMS_PRIMARY"] * 30)
        create_flags.append(out["RDBMS_PRIMARY"].should_create_work_item)
        freqs.append(out["RDBMS_PRIMARY"].freq_in_window)
    # Only the first observation gets the WI lock.
    assert create_flags == [True, False, False, False, False]
    # One observation per call (we collapse duplicates within a single batch).
    assert freqs == [1, 2, 3, 4, 5]


async def test_separate_components_each_get_own_work_item():
    deb = Debouncer(window_seconds=10, threshold=100)
    out = await deb.observe_batch(["RDBMS_A", "MCP_B", "CACHE_C"])
    assert all(r.should_create_work_item for r in out.values())
    assert set(out.keys()) == {"RDBMS_A", "MCP_B", "CACHE_C"}


async def test_lock_releases_after_window():
    deb = Debouncer(window_seconds=1, threshold=100)
    out1 = await deb.observe_batch(["API_X"])
    assert out1["API_X"].should_create_work_item is True

    await asyncio.sleep(1.1)
    out2 = await deb.observe_batch(["API_X"])
    assert out2["API_X"].should_create_work_item is True
