"""Pure policy for the Central Quant static operational runtime mode.

The policy intentionally has no authority over execution, broker settings, or
strategy parameters.  It only decides whether automatic background work that
loads historical state is allowed in the operational process.
"""

from __future__ import annotations

import os
import time


_TRUE_VALUES = frozenset({"1", "true", "yes", "sim", "on"})
_BLOCK_LOG_LAST_EMITTED: dict[str, float] = {}


def _environment_enabled(name: str, environment=None) -> bool:
    """Read a boolean environment flag and fail back to the current runtime."""
    try:
        source = os.environ if environment is None else environment
        value = source.get(name, "false")
        return str(value).strip().lower() in _TRUE_VALUES
    except Exception:
        return False


def static_operational_runtime_enabled() -> bool:
    """Return whether automatic historical background work must be suspended."""
    return _environment_enabled("CENTRAL_STATIC_OPERATIONAL_RUNTIME_ENABLED")


def historical_background_tasks_allowed() -> bool:
    return not static_operational_runtime_enabled()


def heavy_predator_watchdog_audit_allowed() -> bool:
    return historical_background_tasks_allowed()


def auto_learning_runtime_allowed() -> bool:
    return historical_background_tasks_allowed()


def large_redis_snapshot_allowed() -> bool:
    return historical_background_tasks_allowed()


def static_operational_runtime_health() -> dict:
    """Build the in-memory/configuration-only health contract."""
    enabled = static_operational_runtime_enabled()
    return {
        "static_operational_runtime_enabled": enabled,
        "operational_runtime_profile": "STATIC_OPERATIONAL" if enabled else "DEFAULT",
        "historical_background_tasks_enabled": not enabled,
        "predator_heavy_watchdog_audit_enabled": not enabled,
        "auto_learning_runtime_enabled": not enabled,
        "smartpredator_large_redis_snapshot_enabled": not enabled,
        "manual_heavy_audits_available": True,
    }


def static_operational_runtime_startup_summary() -> str:
    policy = static_operational_runtime_health()
    return "\n".join(
        (
            "STATIC OPERATIONAL RUNTIME",
            f"enabled={policy['static_operational_runtime_enabled']}",
            f"historical_background_tasks={policy['historical_background_tasks_enabled']}",
            f"predator_heavy_watchdog_audit={policy['predator_heavy_watchdog_audit_enabled']}",
            f"auto_learning={policy['auto_learning_runtime_enabled']}",
            f"smartpredator_large_redis_snapshot={policy['smartpredator_large_redis_snapshot_enabled']}",
            f"manual_heavy_audits={policy['manual_heavy_audits_available']}",
        )
    )


def static_operational_runtime_should_log_blocked(
    task: str,
    *,
    cooldown_seconds: float = 3600.0,
    now: float | None = None,
) -> bool:
    """Return true at most once per task per cooldown interval."""
    key = str(task or "unknown_task")
    try:
        current = float(time.monotonic() if now is None else now)
        cooldown = max(0.0, float(cooldown_seconds))
    except Exception:
        return True
    previous = _BLOCK_LOG_LAST_EMITTED.get(key)
    if previous is not None and current - previous < cooldown:
        return False
    _BLOCK_LOG_LAST_EMITTED[key] = current
    return True


def static_operational_runtime_blocked_log(task: str, origin: str) -> str:
    return " ".join(
        (
            "STATIC_OPERATIONAL_RUNTIME_BLOCKED",
            f"task={str(task or 'unknown_task')}",
            f"origin={str(origin or 'unknown_origin')}",
            "reason=STATIC_OPERATIONAL_RUNTIME",
        )
    )


def reset_static_operational_runtime_log_state() -> None:
    """Test-only reset for the in-memory log cooldown state."""
    _BLOCK_LOG_LAST_EMITTED.clear()


__all__ = [
    "auto_learning_runtime_allowed",
    "heavy_predator_watchdog_audit_allowed",
    "historical_background_tasks_allowed",
    "large_redis_snapshot_allowed",
    "reset_static_operational_runtime_log_state",
    "static_operational_runtime_blocked_log",
    "static_operational_runtime_enabled",
    "static_operational_runtime_health",
    "static_operational_runtime_should_log_blocked",
    "static_operational_runtime_startup_summary",
]
