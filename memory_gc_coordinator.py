"""Process-local coordination for Central Quant GC and malloc_trim attempts."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional


SKIP_GC_COMPLETED = "gc_completed_while_waiting"
SKIP_RSS_BELOW_THRESHOLD = "rss_below_threshold_after_lock"


def _number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MemoryGCCoordinator:
    """Serialize cleanup attempts and suppress only overlapping duplicates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0

    def coordinate(
        self,
        *,
        reason: str,
        force: bool,
        threshold_mb: float,
        rss_before_mb: Any,
        current_rss_fn: Callable[[], Any],
        collect_fn: Callable[[], Any],
        trim_fn: Callable[[], Any],
    ) -> Dict[str, Any]:
        """Run one coordinated cleanup or return a scalar-only skip result.

        Exceptions from ``collect_fn`` are deliberately not swallowed so each
        caller retains its pre-coordinator error policy.  A trim failure stays
        non-fatal, matching the existing best-effort malloc_trim behavior.
        """

        reason_value = str(reason)
        force_value = bool(force)
        threshold_value = _number_or_none(threshold_mb)
        rss_before_value = _number_or_none(rss_before_mb)
        qualified = force_value or (
            rss_before_value is not None
            and threshold_value is not None
            and rss_before_value >= threshold_value
        )

        result: Dict[str, Any] = {
            "reason": reason_value,
            "force": force_value,
            "qualified": qualified,
            "executed": False,
            "skipped": False,
            "skip_reason": None,
            "rss_before_mb": rss_before_value,
            "rss_recheck_mb": None,
            "waited_ms": None,
            "entry_generation": None,
            "current_generation": None,
            "collected": None,
            "cleanup_elapsed_ms": None,
            "trim_succeeded": None,
            "trim_error": None,
        }
        if not qualified:
            return result

        entry_generation = self._generation
        result["entry_generation"] = entry_generation
        wait_started = time.monotonic()

        with self._lock:
            result["waited_ms"] = round(
                (time.monotonic() - wait_started) * 1000.0,
                2,
            )
            current_generation = self._generation
            result["current_generation"] = current_generation

            try:
                rss_recheck = _number_or_none(current_rss_fn())
            except Exception:
                # A failed diagnostic recheck must not suppress an attempt that
                # was already qualified by the caller's original observation.
                rss_recheck = None
            result["rss_recheck_mb"] = rss_recheck

            if current_generation != entry_generation:
                result["skipped"] = True
                result["skip_reason"] = SKIP_GC_COMPLETED
                return result

            if (
                not force_value
                and rss_recheck is not None
                and threshold_value is not None
                and rss_recheck < threshold_value
            ):
                result["skipped"] = True
                result["skip_reason"] = SKIP_RSS_BELOW_THRESHOLD
                return result

            cleanup_started = time.monotonic()
            collected = collect_fn()
            trim_succeeded = True
            trim_error = None
            try:
                trim_fn()
            except Exception as exc:
                trim_succeeded = False
                trim_error = type(exc).__name__
            cleanup_elapsed_ms = round(
                (time.monotonic() - cleanup_started) * 1000.0,
                2,
            )

            self._generation += 1
            result.update({
                "executed": True,
                "collected": collected,
                "cleanup_elapsed_ms": cleanup_elapsed_ms,
                "trim_succeeded": trim_succeeded,
                "trim_error": trim_error,
                "current_generation": self._generation,
            })

        return result


_PROCESS_MEMORY_GC_COORDINATOR = MemoryGCCoordinator()


def coordinate_memory_gc(**kwargs: Any) -> Dict[str, Any]:
    """Use the one coordinator shared by every integrated process caller."""

    return _PROCESS_MEMORY_GC_COORDINATOR.coordinate(**kwargs)


def emit_memory_gc_skipped(
    result: Dict[str, Any],
    *,
    emit_fn: Callable[..., Any],
) -> bool:
    """Emit the compact skipped event through a fail-open scalar logger."""

    try:
        if not result.get("qualified") or not result.get("skipped"):
            return False
        return bool(emit_fn(
            "MEMORY GC SKIPPED",
            reason=result.get("reason"),
            skip_reason=result.get("skip_reason"),
            rss_before_mb=result.get("rss_before_mb"),
            rss_recheck_mb=result.get("rss_recheck_mb"),
            waited_ms=result.get("waited_ms"),
            entry_generation=result.get("entry_generation"),
            current_generation=result.get("current_generation"),
        ))
    except Exception:
        return False
