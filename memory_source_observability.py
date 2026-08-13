"""Small, fail-open process-memory observations for diagnostic phases.

This module is intentionally stdlib-only and never imports ``main``. Runtime
identity is discovered only from modules that are already loaded.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from itertools import count
from typing import Any


_MEMORY_OBSERVATION_CYCLE_COUNTER = count(1)


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


def start_memory_workload_span() -> dict[str, int | float | None]:
    """Start a scalar-only process RSS span for a diagnostic phase."""

    try:
        rss_start_mb = memory_source_current_rss_mb()
        return {
            "started_at": time.monotonic(),
            "rss_start_mb": rss_start_mb,
        }
    except Exception:
        return {
            "started_at": None,
            "rss_start_mb": None,
        }


def next_memory_observation_cycle_id(prefix: str) -> str:
    """Return one compact process-local correlation id without persistence."""

    try:
        safe_prefix = str(prefix or "memory").strip() or "memory"
        return f"{safe_prefix}-{os.getpid()}-{next(_MEMORY_OBSERVATION_CYCLE_COUNTER)}"
    except Exception:
        return "unknown"


def _emit_memory_phase_observation(
    event_name: str,
    span: dict[str, int | float | None] | None,
    *,
    cycle_id: str,
    ended_at: int | float | None,
    rss_end_mb: int | float | None,
    fields: dict[str, Any],
) -> bool:
    try:
        started_at = span.get("started_at") if isinstance(span, dict) else None
        rss_start_mb = span.get("rss_start_mb") if isinstance(span, dict) else None
        elapsed_ms = (
            round((float(ended_at) - float(started_at)) * 1000.0, 2)
            if isinstance(started_at, (int, float))
            and not isinstance(started_at, bool)
            and isinstance(ended_at, (int, float))
            and not isinstance(ended_at, bool)
            else None
        )
        rss_delta_mb = (
            round(float(rss_end_mb) - float(rss_start_mb), 2)
            if isinstance(rss_start_mb, (int, float))
            and not isinstance(rss_start_mb, bool)
            and isinstance(rss_end_mb, (int, float))
            and not isinstance(rss_end_mb, bool)
            else None
        )
        return emit_memory_source_observation(
            event_name,
            cycle_id=cycle_id,
            elapsed_ms=elapsed_ms,
            rss_start_mb=rss_start_mb,
            rss_end_mb=rss_end_mb,
            rss_delta_mb=rss_delta_mb,
            **fields,
        )
    except Exception:
        return False


def transition_memory_phase_observation(
    event_name: str,
    span: dict[str, int | float | None] | None,
    *,
    cycle_id: str,
    **fields: Any,
) -> dict[str, int | float | None]:
    """Emit one phase and start the next from the exact same RSS boundary."""

    try:
        rss_end_mb = memory_source_current_rss_mb()
        ended_at = time.monotonic()
    except Exception:
        rss_end_mb = None
        ended_at = None

    next_span = {
        "started_at": ended_at,
        "rss_start_mb": rss_end_mb,
    }
    _emit_memory_phase_observation(
        event_name,
        span,
        cycle_id=cycle_id,
        ended_at=ended_at,
        rss_end_mb=rss_end_mb,
        fields=fields,
    )
    return next_span


def finish_memory_phase_observation(
    event_name: str,
    span: dict[str, int | float | None] | None,
    *,
    cycle_id: str,
    **fields: Any,
) -> bool:
    """Finish one scalar-only phase observation; all failures are fail-open."""

    try:
        rss_end_mb = memory_source_current_rss_mb()
        ended_at = time.monotonic()
    except Exception:
        rss_end_mb = None
        ended_at = None
    return _emit_memory_phase_observation(
        event_name,
        span,
        cycle_id=cycle_id,
        ended_at=ended_at,
        rss_end_mb=rss_end_mb,
        fields=fields,
    )


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


__all__ = [
    "emit_memory_source_observation",
    "finish_memory_phase_observation",
    "memory_source_current_rss_mb",
    "next_memory_observation_cycle_id",
    "start_memory_workload_span",
    "transition_memory_phase_observation",
]
