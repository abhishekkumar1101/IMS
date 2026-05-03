"""MTTR (Mean Time To Repair) — calculation utility.

MTTR = end_time (RCA submission) − start_time (first signal).
Stored on the Work Item at close time; this module isolates the math.
"""
from __future__ import annotations

from datetime import datetime


def calculate_mttr_seconds(first_signal_at: datetime, end_time: datetime) -> int:
    delta = (end_time - first_signal_at).total_seconds()
    return max(0, int(delta))


def humanize(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"
