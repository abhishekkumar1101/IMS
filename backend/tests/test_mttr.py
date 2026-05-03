"""MTTR computation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.workflow.mttr import calculate_mttr_seconds, humanize


def test_basic_mttr():
    start = datetime(2026, 5, 2, 10, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=12, seconds=34)
    assert calculate_mttr_seconds(start, end) == 12 * 60 + 34


def test_clamps_negative():
    now = datetime.now(timezone.utc)
    assert calculate_mttr_seconds(now, now - timedelta(seconds=10)) == 0


def test_humanize():
    assert humanize(45) == "45s"
    assert humanize(125) == "2m 5s"
    assert humanize(3661) == "1h 1m"
    assert humanize(90061).startswith("1d ")
