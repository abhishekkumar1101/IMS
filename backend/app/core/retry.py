"""Retry decorator for transient persistence failures.

Wrap any async DB write with `@retry_db` to get exponential backoff +
final exception logging. Used for Postgres + Mongo + Redis writes.
"""
from __future__ import annotations

import logging
from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

log = logging.getLogger("ims.retry")

_RETRYABLE_EXCS = (ConnectionError, TimeoutError, OSError)


def retry_db(attempts: int = 5, max_wait: float = 4.0):
    return retry(
        retry=retry_if_exception_type(_RETRYABLE_EXCS),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.1, max=max_wait),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )


def make_async_retrying(attempts: int = 5, max_wait: float = 4.0) -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception_type(_RETRYABLE_EXCS),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.1, max=max_wait),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
