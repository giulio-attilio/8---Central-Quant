"""Process-local reuse of current-window OHLCV snapshots.

The trading strategies in this repository consume closed candles. A snapshot
is reusable only within the same UTC candle window and only when the exchange
response contains a row for that window (the currently forming candle). This
module deliberately does not cache historical/since queries or custom params.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any


_TIMEFRAME_SECONDS = {
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}
_TIMEFRAME_RE = re.compile(r"^([1-9][0-9]*)([mhd])$")
_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, int], tuple[int, list[list[Any]]]] = {}


def _window(timeframe: str, now_seconds: float) -> tuple[int, int] | None:
    match = _TIMEFRAME_RE.fullmatch(str(timeframe))
    if not match:
        return None
    interval = int(match.group(1)) * _TIMEFRAME_SECONDS[match.group(2)]
    start = int(now_seconds // interval) * interval
    return start * 1000, (start + interval) * 1000


def _copy_rows(rows: list[list[Any]]) -> list[list[Any]]:
    return [list(row) if isinstance(row, (list, tuple)) else row for row in rows]


def get_cached_ohlcv_snapshot(
    symbol: str,
    timeframe: str,
    limit: int | None,
    *,
    now_seconds: float | None = None,
) -> list[list[Any]] | None:
    """Return a defensive copy from this candle window, if it can satisfy limit."""
    if not symbol or not isinstance(limit, int) or limit <= 0:
        return None
    now = time.time() if now_seconds is None else float(now_seconds)
    window = _window(timeframe, now)
    if window is None:
        return None
    start_ms, end_ms = window
    key = (str(symbol).upper(), str(timeframe), start_ms)
    with _CACHE_LOCK:
        expired = [
            cache_key
            for cache_key, (valid_until, _) in _CACHE.items()
            if now * 1000 >= valid_until
        ]
        for cache_key in expired:
            _CACHE.pop(cache_key, None)
        entry = _CACHE.get(key)
        if entry is None or now * 1000 >= min(entry[0], end_ms):
            return None
        rows = entry[1]
        if len(rows) < limit:
            return None
        return _copy_rows(rows[-limit:])


def store_ohlcv_snapshot(
    symbol: str,
    timeframe: str,
    rows: Any,
    *,
    requested_window_start_ms: int,
    now_seconds: float | None = None,
) -> bool:
    """Store only successful snapshots whose final row is this window's candle."""
    if not symbol or not isinstance(rows, (list, tuple)) or not rows:
        return False
    now = time.time() if now_seconds is None else float(now_seconds)
    window = _window(timeframe, now)
    if window is None:
        return False
    start_ms, end_ms = window
    if start_ms != int(requested_window_start_ms) or now * 1000 >= end_ms:
        return False
    try:
        if int(rows[-1][0]) != start_ms:
            return False
        snapshot = _copy_rows(list(rows))
    except (IndexError, TypeError, ValueError, OverflowError):
        return False
    key = (str(symbol).upper(), str(timeframe), start_ms)
    with _CACHE_LOCK:
        old = _CACHE.get(key)
        if old is None or len(snapshot) > len(old[1]):
            _CACHE[key] = (end_ms, snapshot)
    return True


def current_ohlcv_window_start_ms(
    timeframe: str, *, now_seconds: float | None = None
) -> int | None:
    """Expose the current UTC candle-window anchor for the exchange wrapper."""
    now = time.time() if now_seconds is None else float(now_seconds)
    window = _window(timeframe, now)
    return window[0] if window else None


def clear_ohlcv_candle_cache_for_tests() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


__all__ = [
    "clear_ohlcv_candle_cache_for_tests",
    "current_ohlcv_window_start_ms",
    "get_cached_ohlcv_snapshot",
    "store_ohlcv_snapshot",
]
