"""Small, fail-open process-memory spans for existing full-file reads.

This module is intentionally stdlib-only and never imports ``main``. Runtime
identity is discovered only from modules that are already loaded.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from typing import Any


REGISTRY_V2_WAL_MEMORY_WINDOW_SECONDS = 60.0
_REGISTRY_V2_WAL_MEMORY_LOCK = threading.Lock()
_REGISTRY_V2_WAL_MEMORY_STATE = {
    "window_started": None,
    "calls": 0,
    "max_journal_bytes": None,
    "max_event_count": None,
    "max_rss_delta_mb": None,
    "max_elapsed_ms": None,
    "last_rss_before_mb": None,
    "last_rss_after_mb": None,
}


def memory_source_current_rss_mb() -> float | None:
    """Return current Linux process RSS without importing operational code."""

    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(float(line.split()[1]) / 1024.0, 2)
    except Exception:
        return None
    return None


def _sampled_at() -> str:
    try:
        return datetime.now().astimezone().isoformat(timespec="milliseconds")
    except Exception:
        return "unknown"


def _runtime_boot_id() -> str:
    try:
        for module_name in ("__main__", "main"):
            module = sys.modules.get(module_name)
            value = getattr(module, "CENTRAL_RUNTIME_BOOT_ID", None) if module is not None else None
            if value:
                return str(value)
    except Exception:
        pass
    return "unknown"


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return "unsupported"


def emit_memory_source_observation(event_name: str, **fields: Any) -> bool:
    """Print one compact scalar-only event; observability failures are ignored."""

    try:
        values = {
            "sampled_at": _sampled_at(),
            **{str(key): _scalar(value) for key, value in fields.items()},
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "thread": threading.current_thread().name,
            "boot_id": _runtime_boot_id(),
        }
        rendered = " | ".join(
            f"{key}={'unknown' if value is None else value}"
            for key, value in values.items()
        )
        print(f"{event_name} | {rendered}", flush=True)
        return True
    except Exception:
        return False


def _max_scalar(current: Any, candidate: Any) -> int | float | None:
    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
        return current
    if not isinstance(current, (int, float)) or isinstance(current, bool):
        return candidate
    return max(current, candidate)


def observe_registry_v2_wal_memory(**fields: Any) -> bool:
    """Aggregate hot-path WAL spans and emit at most once per process/minute."""

    try:
        observed_at = time.monotonic()
        emission = None
        with _REGISTRY_V2_WAL_MEMORY_LOCK:
            state = _REGISTRY_V2_WAL_MEMORY_STATE
            if state["window_started"] is None:
                state["window_started"] = observed_at
            state["calls"] += 1
            state["max_journal_bytes"] = _max_scalar(
                state["max_journal_bytes"], fields.get("journal_bytes")
            )
            state["max_event_count"] = _max_scalar(
                state["max_event_count"], fields.get("event_count")
            )
            state["max_rss_delta_mb"] = _max_scalar(
                state["max_rss_delta_mb"], fields.get("rss_delta_mb")
            )
            state["max_elapsed_ms"] = _max_scalar(
                state["max_elapsed_ms"], fields.get("elapsed_ms")
            )
            state["last_rss_before_mb"] = _scalar(fields.get("rss_before_mb"))
            state["last_rss_after_mb"] = _scalar(fields.get("rss_after_mb"))

            if observed_at - state["window_started"] >= REGISTRY_V2_WAL_MEMORY_WINDOW_SECONDS:
                emission = {
                    "window_seconds": int(REGISTRY_V2_WAL_MEMORY_WINDOW_SECONDS),
                    "calls": state["calls"],
                    "max_journal_bytes": state["max_journal_bytes"],
                    "max_event_count": state["max_event_count"],
                    "max_rss_delta_mb": state["max_rss_delta_mb"],
                    "max_elapsed_ms": state["max_elapsed_ms"],
                    "last_rss_before_mb": state["last_rss_before_mb"],
                    "last_rss_after_mb": state["last_rss_after_mb"],
                }
                state.update({
                    "window_started": observed_at,
                    "calls": 0,
                    "max_journal_bytes": None,
                    "max_event_count": None,
                    "max_rss_delta_mb": None,
                    "max_elapsed_ms": None,
                    "last_rss_before_mb": None,
                    "last_rss_after_mb": None,
                })
        if emission is None:
            return False
        return emit_memory_source_observation(
            "REGISTRY_V2_WAL_MEMORY",
            **emission,
        )
    except Exception:
        return False


__all__ = [
    "emit_memory_source_observation",
    "memory_source_current_rss_mb",
    "observe_registry_v2_wal_memory",
]
