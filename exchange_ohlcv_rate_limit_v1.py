"""Process-wide pacing for BingX OHLCV requests shared by scanner threads."""

from __future__ import annotations

import threading
import time


# BingX's published swap-kline IP limit is one request per second. A small
# margin avoids sliding-window boundary bursts while remaining near that cap.
MIN_OHLCV_REQUEST_INTERVAL_SECONDS = 1.05
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_STARTED_AT = 0.0
_TICKER_RATE_LOCK = threading.Lock()
_LAST_TICKER_REQUEST_STARTED_AT = 0.0


def wait_for_exchange_ohlcv_slot() -> float:
    """Wait until the next shared OHLCV request may start; return wait seconds."""
    global _LAST_REQUEST_STARTED_AT

    with _RATE_LOCK:
        now = time.monotonic()
        delay = max(
            0.0,
            MIN_OHLCV_REQUEST_INTERVAL_SECONDS - (now - _LAST_REQUEST_STARTED_AT),
        )
        if delay:
            time.sleep(delay)
        _LAST_REQUEST_STARTED_AT = time.monotonic()
        return delay


def wait_for_exchange_ticker_slot() -> float:
    """Pace BingX ticker requests independently from kline requests."""
    global _LAST_TICKER_REQUEST_STARTED_AT

    with _TICKER_RATE_LOCK:
        now = time.monotonic()
        delay = max(
            0.0,
            MIN_OHLCV_REQUEST_INTERVAL_SECONDS
            - (now - _LAST_TICKER_REQUEST_STARTED_AT),
        )
        if delay:
            time.sleep(delay)
        _LAST_TICKER_REQUEST_STARTED_AT = time.monotonic()
        return delay


def reset_exchange_ohlcv_rate_limit_for_tests() -> None:
    """Reset process-local pacing state for deterministic offline tests."""
    global _LAST_REQUEST_STARTED_AT, _LAST_TICKER_REQUEST_STARTED_AT
    with _RATE_LOCK:
        _LAST_REQUEST_STARTED_AT = 0.0
    with _TICKER_RATE_LOCK:
        _LAST_TICKER_REQUEST_STARTED_AT = 0.0


__all__ = [
    "MIN_OHLCV_REQUEST_INTERVAL_SECONDS",
    "reset_exchange_ohlcv_rate_limit_for_tests",
    "wait_for_exchange_ohlcv_slot",
    "wait_for_exchange_ticker_slot",
]
