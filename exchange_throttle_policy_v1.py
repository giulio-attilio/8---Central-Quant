"""Small fail-closed classifiers for exchange throttling responses."""

from __future__ import annotations

import re
import threading
import time


_BINGX_THROTTLE_CODE = re.compile(r"(?:\"code\"\s*:\s*100410|\b100410\b)")
_HTTP_429 = re.compile(r"(?:\bhttp\s*429\b|\b429\s+too\s+many\s+requests\b)", re.IGNORECASE)
_COOLDOWN_LOCK = threading.Lock()
_COOLDOWN_UNTIL = 0.0
_THROTTLE_BACKOFF_SECONDS = 0.0
DEFAULT_COOLDOWN_SECONDS = 60.0
MAX_COOLDOWN_SECONDS = 300.0


def is_exchange_throttle_error(exc: BaseException) -> bool:
    """Recognize explicit throttling so scanners do not amplify it with retries."""
    if not isinstance(exc, BaseException):
        return False
    type_name = type(exc).__name__.lower()
    if type_name in {"ratelimitexceeded", "ddosprotection"}:
        return True
    try:
        message = str(exc)
    except Exception:
        return False
    return bool(_BINGX_THROTTLE_CODE.search(message) or _HTTP_429.search(message))


def start_exchange_throttle_cooldown(seconds: float = DEFAULT_COOLDOWN_SECONDS) -> float:
    """Open a short process-wide circuit for shared public OHLCV reads."""
    global _COOLDOWN_UNTIL
    duration = max(0.0, min(float(seconds), MAX_COOLDOWN_SECONDS))
    now = time.monotonic()
    with _COOLDOWN_LOCK:
        _COOLDOWN_UNTIL = max(_COOLDOWN_UNTIL, now + duration)
        return max(0.0, _COOLDOWN_UNTIL - now)


def record_exchange_throttle_cooldown() -> float:
    """Increase bounded backoff after each consecutive explicit throttle."""
    global _COOLDOWN_UNTIL, _THROTTLE_BACKOFF_SECONDS
    now = time.monotonic()
    with _COOLDOWN_LOCK:
        if _THROTTLE_BACKOFF_SECONDS <= 0.0:
            _THROTTLE_BACKOFF_SECONDS = DEFAULT_COOLDOWN_SECONDS
        else:
            _THROTTLE_BACKOFF_SECONDS = min(
                MAX_COOLDOWN_SECONDS, _THROTTLE_BACKOFF_SECONDS * 2.0
            )
        _COOLDOWN_UNTIL = max(
            _COOLDOWN_UNTIL, now + _THROTTLE_BACKOFF_SECONDS
        )
        return max(0.0, _COOLDOWN_UNTIL - now)


def reset_exchange_throttle_backoff() -> None:
    """Reset consecutive-throttle backoff after a successful shared OHLCV read."""
    global _THROTTLE_BACKOFF_SECONDS
    with _COOLDOWN_LOCK:
        _THROTTLE_BACKOFF_SECONDS = 0.0


def exchange_throttle_cooldown_remaining() -> float:
    now = time.monotonic()
    with _COOLDOWN_LOCK:
        return max(0.0, _COOLDOWN_UNTIL - now)


def reset_exchange_throttle_cooldown_for_tests() -> None:
    global _COOLDOWN_UNTIL, _THROTTLE_BACKOFF_SECONDS
    with _COOLDOWN_LOCK:
        _COOLDOWN_UNTIL = 0.0
        _THROTTLE_BACKOFF_SECONDS = 0.0


__all__ = [
    "DEFAULT_COOLDOWN_SECONDS",
    "MAX_COOLDOWN_SECONDS",
    "exchange_throttle_cooldown_remaining",
    "is_exchange_throttle_error",
    "record_exchange_throttle_cooldown",
    "reset_exchange_throttle_backoff",
    "reset_exchange_throttle_cooldown_for_tests",
    "start_exchange_throttle_cooldown",
]
