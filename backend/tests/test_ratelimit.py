"""In-memory token-bucket behaviour under burst."""
from __future__ import annotations

import pytest

from app.core.ratelimit import InMemoryTokenBucket


async def test_capacity_then_refusal():
    bucket = InMemoryTokenBucket(capacity=10, refill_per_sec=10)
    allows = []
    for _ in range(15):
        allowed, _ = await bucket.consume("client-1", cost=1, now_ms=1000)
        allows.append(allowed)
    assert sum(allows) == 10
    assert allows[:10] == [True] * 10
    assert allows[10:] == [False] * 5


async def test_refill_over_time():
    bucket = InMemoryTokenBucket(capacity=5, refill_per_sec=5)
    for _ in range(5):
        allowed, _ = await bucket.consume("c", cost=1, now_ms=0)
        assert allowed
    allowed, _ = await bucket.consume("c", cost=1, now_ms=0)
    assert not allowed
    # Advance one second → 5 tokens refilled.
    allowed, _ = await bucket.consume("c", cost=1, now_ms=1000)
    assert allowed


async def test_isolated_clients():
    bucket = InMemoryTokenBucket(capacity=2, refill_per_sec=1)
    a1, _ = await bucket.consume("a", cost=2, now_ms=0)
    b1, _ = await bucket.consume("b", cost=2, now_ms=0)
    assert a1 and b1
    a2, _ = await bucket.consume("a", cost=1, now_ms=0)
    b2, _ = await bucket.consume("b", cost=1, now_ms=0)
    assert (a2, b2) == (False, False)
