"""Pure policy contract for automatic heavy learning refreshes."""

from __future__ import annotations

import os


_TRUE_VALUES = frozenset({"1", "true", "yes", "sim", "on"})


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in _TRUE_VALUES


CENTRAL_AUTO_LEARNING_REFRESH_ENABLED = _env_enabled(
    "CENTRAL_AUTO_LEARNING_REFRESH_ENABLED"
)


def automatic_learning_refresh_enabled(legacy_enabled: bool = True) -> bool:
    """Require the global policy and preserve the legacy disable switch."""
    return CENTRAL_AUTO_LEARNING_REFRESH_ENABLED and bool(legacy_enabled)


def automatic_learning_refresh_health(
    *,
    interval_seconds: int = 900,
    thread_started: bool = False,
    legacy_enabled: bool = True,
) -> dict:
    """Return policy-only health without importing or running learning code."""
    enabled = automatic_learning_refresh_enabled(legacy_enabled)
    return {
        "auto_learning_refresh_enabled": enabled,
        "auto_learning_refresh_thread_started": bool(thread_started) if enabled else False,
        "auto_learning_refresh_manual_available": True,
        "auto_learning_refresh_interval_seconds": int(interval_seconds),
        "auto_learning_refresh_disabled_reason": None if enabled else "DISABLED_BY_POLICY",
    }


__all__ = [
    "CENTRAL_AUTO_LEARNING_REFRESH_ENABLED",
    "automatic_learning_refresh_enabled",
    "automatic_learning_refresh_health",
]
