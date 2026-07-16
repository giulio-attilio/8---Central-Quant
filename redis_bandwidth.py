"""Low-overhead Redis bandwidth observability and conservative traffic diet.

The module never creates a Redis client and never performs work at import time.
Callers explicitly pass their existing client.  Instrumentation stores only
aggregated sizes and sanitized key names; values are never retained in metrics.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import deque
from datetime import date, datetime, timezone
from typing import Any, Deque, Dict, Iterable, Mapping, Optional, Tuple


VERSION = "2.0.0"
DEFAULT_TOP_LIMIT = 20
DEFAULT_MAX_CARDINALITY = 512
DEFAULT_MAX_RUNTIME_KEYS = 256
DEFAULT_DAILY_FLAG_TTL_SECONDS = 45 * 24 * 60 * 60
DEFAULT_SAFE_CACHE_SECONDS = 5.0
HISTORY_HOT_KEY_CACHE_SECONDS = 60.0
PAPER_POSITION_CACHE_SECONDS = 15.0

HOT_KEY_POLICIES: Dict[str, Dict[str, Any]] = {
    "falcon:events": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "turtle_pro:events": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "smartpredator:positions": {"policy": "PAPER_POSITION_CACHE_LIVE_FRESH", "cache_seconds": PAPER_POSITION_CACHE_SECONDS},
    "turtle_pro:trades": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "turtle_pro:signals": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "falcon:signals": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "donkey:positions": {"policy": "PAPER_POSITION_CACHE_LIVE_FRESH", "cache_seconds": PAPER_POSITION_CACHE_SECONDS},
    "falcon:trades": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "donkey:trades": {"policy": "HISTORY_CACHE", "cache_seconds": HISTORY_HOT_KEY_CACHE_SECONDS},
    "cobra:positions": {"policy": "PAPER_POSITION_CACHE_LIVE_FRESH", "cache_seconds": PAPER_POSITION_CACHE_SECONDS},
}

_TRUE_VALUES = {"1", "true", "yes", "sim", "on"}
_UUID_OR_LONG_ID = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{16,}|[A-Za-z0-9_-]{32,})$",
    re.IGNORECASE,
)
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_lock = threading.RLock()
_metrics: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
_largest_payloads: Deque[Dict[str, Any]] = deque(maxlen=100)
_cache: Dict[Tuple[int, str], Dict[str, Any]] = {}
_last_values: Dict[Tuple[int, str], Dict[str, Any]] = {}
_ttl_applied: Dict[str, int] = {}
_started_at = datetime.now(timezone.utc).isoformat()
_cache_hits = 0
_sets_skipped = 0
_bytes_avoided = 0
_cache_bytes_avoided = 0
_set_bytes_avoided = 0
_instrumentation_errors = 0
_last_error: Optional[str] = None


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in _TRUE_VALUES


def instrumentation_enabled() -> bool:
    """Return the feature flag dynamically so tests and runtime can toggle it."""
    return _env_flag("REDIS_BANDWIDTH_INSTRUMENTATION_ENABLED", False)


def bandwidth_diet_enabled() -> bool:
    """Traffic reductions are enabled unless explicitly disabled."""
    return _env_flag("REDIS_BANDWIDTH_DIET_ENABLED", True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, str):
        return len(value.encode("utf-8", errors="replace"))
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        encoded = str(value)
    return len(encoded.encode("utf-8", errors="replace"))


def _value_digest(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8", errors="replace")
    else:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def sanitize_redis_key(key: Any) -> str:
    """Keep useful key categories while masking IDs and suspicious material."""
    text = str(key or "<empty>").strip()
    lowered = text.lower()
    if "://" in text or any(marker in lowered for marker in ("password=", "token=", "secret=")):
        return "<redacted-key>"
    parts = []
    for raw_part in text.split(":")[:8]:
        part = raw_part.strip()
        if _ISO_DAY.fullmatch(part):
            parts.append(part)
        elif _UUID_OR_LONG_ID.fullmatch(part) or (part.isdigit() and len(part) >= 8):
            parts.append("<id>")
        elif len(part) > 48:
            parts.append(part[:16] + "<masked>")
        else:
            parts.append(part)
    if text.count(":") >= 8:
        parts.append("<more>")
    return ":".join(parts) or "<empty>"


def sanitize_caller(caller: Any) -> str:
    text = str(caller or "UNKNOWN").strip()
    if not text:
        return "UNKNOWN"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)[:96]


def classify_redis_key(key: Any) -> Dict[str, Any]:
    """Classify known Central Quant keys without querying Redis."""
    sanitized = sanitize_redis_key(key)
    lowered = sanitized.lower()
    permanent_markers = (
        "registry",
        "lifecycle",
        "tombstone",
        ":positions",
        ":trades",
        ":signals",
        ":state",
        "cooldown",
        "reentry",
        "offset",
        ":lock",
        "confirmed",
        "be_monitor",
        "sweep_state",
    )
    temporary_markers = (
        "daily_summary_sent",
        "funnel",
        "heartbeat",
        "last_scanned",
        "startup_message",
        "startup_msg",
        "management_alert_guard",
        "execution_firewall_events",
        ":events",
        "boot_history",
    )
    if any(marker in lowered for marker in permanent_markers):
        classification = "PERMANENT"
    elif any(marker in lowered for marker in temporary_markers):
        classification = "TEMPORARY"
    else:
        classification = "UNKNOWN"
    ttl = DEFAULT_DAILY_FLAG_TTL_SECONDS if "daily_summary_sent" in lowered else None
    return {
        "key": sanitized,
        "classification": classification,
        "ttl_seconds": ttl,
        "reason": (
            "known daily delivery flag"
            if ttl
            else "known source-of-truth or operational state"
            if classification == "PERMANENT"
            else "known transient/reporting state"
            if classification == "TEMPORARY"
            else "unknown key; no automatic TTL"
        ),
    }


def _execution_mode_for_caller(caller: Any) -> str:
    """Resolve only public mode flags; never read credentials or mutate env."""
    name = sanitize_caller(caller).lower()
    if name.endswith("falcon"):
        value = os.environ.get("FALCON_MODE") or os.environ.get("EXECUTION_MODE")
    elif name.endswith("predator"):
        value = os.environ.get("PREDATOR_MODE") or os.environ.get("SMART_PREDATOR_MODE")
    elif name.endswith("meme") or name.endswith("turtle"):
        value = "PAPER"
    else:
        value = os.environ.get("EXECUTION_MODE")
    return str(value or "PAPER").strip().upper()


def safe_cache_seconds_for_key(
    key: Any,
    *,
    execution_mode: Optional[str] = None,
    critical: bool = False,
) -> float:
    """Return the conservative V2 cache policy for one key and context."""
    if critical:
        return 0.0
    lowered = sanitize_redis_key(key).lower()
    if lowered.endswith((":events", ":trades", ":signals")) or "execution_firewall_events" in lowered:
        return HISTORY_HOT_KEY_CACHE_SECONDS
    if lowered.endswith(":positions"):
        mode = str(execution_mode or "UNKNOWN").strip().upper()
        if mode in {"PAPER", "VERIFY", "DRY_RUN", "OBSERVATION_ONLY"}:
            return PAPER_POSITION_CACHE_SECONDS
        return 0.0
    if any(marker in lowered for marker in ("funnel", "boot_history", "last_scanned")):
        return 30.0
    return 0.0


def redis_key_requires_fresh_read(key: Any, *, execution_mode: Optional[str] = None) -> bool:
    """Make the LIVE position freshness rule explicit and independently testable."""
    lowered = sanitize_redis_key(key).lower()
    mode = str(execution_mode or "UNKNOWN").strip().upper()
    return lowered.endswith(":positions") and mode not in {
        "PAPER",
        "VERIFY",
        "DRY_RUN",
        "OBSERVATION_ONLY",
    }


def ttl_seconds_for_key(key: Any) -> Optional[int]:
    return classify_redis_key(key).get("ttl_seconds")


def _bounded_metric_key(op: str, key: str, caller: str) -> Tuple[str, str, str]:
    configured = os.environ.get("REDIS_BANDWIDTH_MAX_CARDINALITY")
    try:
        maximum = max(32, int(configured or DEFAULT_MAX_CARDINALITY))
    except (TypeError, ValueError):
        maximum = DEFAULT_MAX_CARDINALITY
    candidate = (op, key, caller)
    if candidate in _metrics or len(_metrics) < maximum:
        return candidate
    return (op, "<other-keys>", caller)


def _trim_runtime_maps() -> None:
    """Bound local cache/checksum cardinality without persisting any values."""
    configured = os.environ.get("REDIS_BANDWIDTH_MAX_RUNTIME_KEYS")
    try:
        maximum = max(32, int(configured or DEFAULT_MAX_RUNTIME_KEYS))
    except (TypeError, ValueError):
        maximum = DEFAULT_MAX_RUNTIME_KEYS
    while len(_cache) > maximum:
        _cache.pop(next(iter(_cache)))
    while len(_last_values) > maximum:
        _last_values.pop(next(iter(_last_values)))


def _record_operation(
    op: str,
    key: Any,
    caller: Any,
    *,
    bytes_in: int = 0,
    bytes_out: int = 0,
    payload_bytes: int = 0,
    ttl_seconds: Optional[int] = None,
) -> None:
    """Record aggregate metadata only; never retain values."""
    global _instrumentation_errors, _last_error
    if not instrumentation_enabled():
        return
    try:
        now = _utc_now()
        operation = str(op or "UNKNOWN").upper()
        safe_key = sanitize_redis_key(key)
        safe_caller = sanitize_caller(caller)
        with _lock:
            metric_key = _bounded_metric_key(operation, safe_key, safe_caller)
            entry = _metrics.setdefault(
                metric_key,
                {
                    "op": operation,
                    "key": metric_key[1],
                    "caller": safe_caller,
                    "bytes_in": 0,
                    "bytes_out": 0,
                    "total_bytes": 0,
                    "count": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "max_payload_bytes": 0,
                    "ttl_seconds": ttl_seconds,
                },
            )
            entry["count"] += 1
            entry["bytes_in"] += max(0, int(bytes_in))
            entry["bytes_out"] += max(0, int(bytes_out))
            entry["total_bytes"] += max(0, int(bytes_in)) + max(0, int(bytes_out))
            entry["max_payload_bytes"] = max(entry["max_payload_bytes"], max(0, int(payload_bytes)))
            entry["last_seen"] = now
            if ttl_seconds is not None:
                entry["ttl_seconds"] = ttl_seconds
            if payload_bytes > 0:
                _largest_payloads.append(
                    {
                        "op": operation,
                        "key": safe_key,
                        "caller": safe_caller,
                        "payload_bytes": int(payload_bytes),
                        "timestamp": now,
                    }
                )
    except Exception as exc:  # metrics are strictly fail-open
        with _lock:
            _instrumentation_errors += 1
            _last_error = f"instrumentation_error:{type(exc).__name__}"


def _record_internal_error(exc: Exception) -> None:
    global _instrumentation_errors, _last_error
    with _lock:
        _instrumentation_errors += 1
        _last_error = f"{type(exc).__name__}: internal observability failure"


def redis_get(
    client: Any,
    key: Any,
    *,
    caller: str = "UNKNOWN",
    cache_ttl_seconds: Optional[float] = None,
    no_cache: bool = False,
) -> Any:
    """Call ``GET`` with optional safe local caching and aggregate metrics."""
    global _cache_hits, _bytes_avoided, _cache_bytes_avoided
    cache_key = (id(client), str(key))
    inferred_mode = _execution_mode_for_caller(caller)
    ttl = (
        safe_cache_seconds_for_key(key, execution_mode=inferred_mode)
        if cache_ttl_seconds is None
        else max(0.0, float(cache_ttl_seconds))
    )
    if no_cache or not bandwidth_diet_enabled():
        ttl = 0.0
    now_mono = time.monotonic()
    if ttl > 0:
        try:
            with _lock:
                cached = _cache.get(cache_key)
                if cached and cached.get("client") is client and now_mono - cached["stored_at"] <= ttl:
                    _cache_hits += 1
                    avoided = _payload_size(cached["value"])
                    _cache_bytes_avoided += avoided
                    _bytes_avoided += avoided
                    return cached["value"]
        except Exception as exc:
            _record_internal_error(exc)

    value = client.get(key)
    size = _payload_size(value)
    try:
        digest = _value_digest(value)
        with _lock:
            _last_values[cache_key] = {
                "client": client,
                "digest": digest,
                "seen_at": now_mono,
                "source": "GET",
            }
            if ttl > 0:
                _cache[cache_key] = {"client": client, "value": value, "stored_at": now_mono}
            _trim_runtime_maps()
        _record_operation("GET", key, caller, bytes_out=size, payload_bytes=size)
    except Exception as exc:
        _record_internal_error(exc)
    return value


def redis_set(
    client: Any,
    key: Any,
    value: Any,
    *,
    caller: str = "UNKNOWN",
    skip_unchanged: bool = True,
    ttl_seconds: Optional[int] = None,
    cache_ttl_seconds: Optional[float] = None,
) -> Any:
    """Call ``SET`` while avoiding a locally confirmed identical rewrite.

    No comparison ``GET`` is issued.  A skip is possible only after this process
    observed the exact value through a successful GET or SET.
    """
    global _sets_skipped, _bytes_avoided, _set_bytes_avoided
    cache_key = (id(client), str(key))
    size = _payload_size(value)
    digest: Optional[str] = None
    try:
        digest = _value_digest(value)
    except Exception as exc:
        _record_internal_error(exc)

    should_skip = False
    if bandwidth_diet_enabled() and skip_unchanged and digest is not None:
        try:
            with _lock:
                previous = _last_values.get(cache_key)
                should_skip = bool(
                    previous
                    and previous.get("client") is client
                    and previous.get("digest") == digest
                )
                if should_skip:
                    _sets_skipped += 1
                    _set_bytes_avoided += size
                    _bytes_avoided += size
        except Exception as exc:
            _record_internal_error(exc)

    effective_ttl = ttl_seconds if ttl_seconds is not None else ttl_seconds_for_key(key)
    if should_skip:
        _record_operation("SET_SKIPPED", key, caller, payload_bytes=size)
        if effective_ttl is not None and int(effective_ttl) > 0:
            try:
                client.expire(key, int(effective_ttl))
                safe_key = sanitize_redis_key(key)
                with _lock:
                    _ttl_applied[safe_key] = int(effective_ttl)
                _record_operation(
                    "EXPIRE",
                    key,
                    caller,
                    bytes_in=_payload_size(str(effective_ttl)),
                    payload_bytes=_payload_size(str(effective_ttl)),
                    ttl_seconds=int(effective_ttl),
                )
            except Exception as exc:
                _record_internal_error(exc)
        return True

    result = client.set(key, value)
    now_mono = time.monotonic()
    try:
        with _lock:
            if digest is not None:
                _last_values[cache_key] = {
                    "client": client,
                    "digest": digest,
                    "seen_at": now_mono,
                    "source": "SET",
                }
            inferred_mode = _execution_mode_for_caller(caller)
            safe_cache_seconds = (
                safe_cache_seconds_for_key(key, execution_mode=inferred_mode)
                if cache_ttl_seconds is None
                else max(0.0, float(cache_ttl_seconds))
            ) if bandwidth_diet_enabled() else 0.0
            if safe_cache_seconds > 0:
                _cache[cache_key] = {"client": client, "value": value, "stored_at": now_mono}
            else:
                _cache.pop(cache_key, None)
            _trim_runtime_maps()
        _record_operation("SET", key, caller, bytes_in=size, payload_bytes=size)
    except Exception as exc:
        _record_internal_error(exc)

    if effective_ttl is not None and int(effective_ttl) > 0:
        try:
            client.expire(key, int(effective_ttl))
            safe_key = sanitize_redis_key(key)
            with _lock:
                _ttl_applied[safe_key] = int(effective_ttl)
            _record_operation(
                "EXPIRE",
                key,
                caller,
                bytes_in=_payload_size(str(effective_ttl)),
                payload_bytes=_payload_size(str(effective_ttl)),
                ttl_seconds=int(effective_ttl),
            )
        except Exception as exc:
            # A TTL failure must not change the already successful SET contract.
            _record_internal_error(exc)
    return result


def invalidate_redis_cache(client: Any, key: Any) -> None:
    with _lock:
        _cache.pop((id(client), str(key)), None)


def _aggregate(entries: Iterable[Mapping[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for item in entries:
        name = str(item.get(field) or "UNKNOWN")
        row = output.setdefault(name, {field: name, "count": 0, "total_bytes": 0, "max_payload_bytes": 0})
        row["count"] += int(item.get("count") or 0)
        row["total_bytes"] += int(item.get("total_bytes") or 0)
        row["max_payload_bytes"] = max(row["max_payload_bytes"], int(item.get("max_payload_bytes") or 0))
    return output


def _top(rows: Iterable[Mapping[str, Any]], *, limit: int, sort_field: str) -> list[Dict[str, Any]]:
    return [dict(item) for item in sorted(rows, key=lambda item: int(item.get(sort_field) or 0), reverse=True)[:limit]]


def _old_daily_flags(keys: Iterable[str]) -> list[str]:
    cutoff_days = DEFAULT_DAILY_FLAG_TTL_SECONDS // 86400
    result = []
    today = date.today()
    for key in keys:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", key)
        if not match or "daily_summary_sent" not in key.lower():
            continue
        try:
            age = (today - date.fromisoformat(match.group(1))).days
        except ValueError:
            continue
        if age > cutoff_days:
            result.append(key)
    return sorted(set(result))


def redis_bandwidth_report(limit: int = DEFAULT_TOP_LIMIT) -> Dict[str, Any]:
    """Return an in-memory diagnostic snapshot without querying Redis."""
    if not isinstance(limit, int) or limit < 1:
        raise TypeError("limit must be a positive int")
    limit = min(limit, 100)
    with _lock:
        entries = [dict(item) for item in _metrics.values()]
        for item in entries:
            count = max(1, int(item.get("count") or 0))
            item["avg_payload_bytes"] = round(int(item.get("total_bytes") or 0) / count, 2)
        largest = sorted((dict(item) for item in _largest_payloads), key=lambda item: item["payload_bytes"], reverse=True)[:limit]
        ttl_applied = dict(_ttl_applied)
        cache_hits = _cache_hits
        sets_skipped = _sets_skipped
        bytes_avoided = _bytes_avoided
        cache_bytes_avoided = _cache_bytes_avoided
        set_bytes_avoided = _set_bytes_avoided
        errors = _instrumentation_errors
        last_error = _last_error

    keys_by_bytes = _aggregate(entries, "key")
    operations = _aggregate(entries, "op")
    callers = _aggregate(entries, "caller")
    for rows in (keys_by_bytes, operations, callers):
        for row in rows.values():
            count = max(1, int(row.get("count") or 0))
            row["avg_payload_bytes"] = round(int(row.get("total_bytes") or 0) / count, 2)
    observed_keys = sorted(keys_by_bytes)
    temporary_without_ttl = []
    for key in observed_keys:
        classification = classify_redis_key(key)
        if classification["classification"] == "TEMPORARY" and key not in ttl_applied:
            temporary_without_ttl.append(classification)

    total_ops = sum(int(item.get("count") or 0) for item in entries)
    total_bytes = sum(int(item.get("total_bytes") or 0) for item in entries)
    potential_total = total_bytes + bytes_avoided
    savings_pct = round((bytes_avoided / potential_total * 100.0), 2) if potential_total else 0.0
    warnings = []
    recommendations = []
    if not instrumentation_enabled():
        warnings.append("Instrumentation is disabled; enable REDIS_BANDWIDTH_INSTRUMENTATION_ENABLED to collect aggregates.")
    if errors:
        warnings.append(f"Instrumentation recorded {errors} internal fail-open error(s).")
    if temporary_without_ttl:
        recommendations.append("Review observed temporary keys without a known TTL; no TTL was applied automatically.")
    top_key_rows = _top(keys_by_bytes.values(), limit=limit, sort_field="total_bytes")
    if top_key_rows:
        recommendations.append(f"Prioritize repeated reads/writes for {top_key_rows[0]['key']}.")
    for row in top_key_rows[:5]:
        key = row["key"]
        policy = HOT_KEY_POLICIES.get(key)
        if policy:
            recommendations.append(
                f"{key}: V2 {policy['policy']} active ({policy['cache_seconds']:g}s); "
                f"observed average {row['avg_payload_bytes']} bytes/call."
            )
    if sets_skipped:
        recommendations.append(f"Keep skip-unchanged enabled; {sets_skipped} identical SET operation(s) were avoided.")
    if cache_hits:
        recommendations.append(f"Short safe caches avoided {cache_hits} Redis GET operation(s).")
    if not recommendations:
        recommendations.append("Collect a representative window before changing source-of-truth keys or execution paths.")

    top_hot_keys_status = []
    for key, policy in HOT_KEY_POLICIES.items():
        observed = keys_by_bytes.get(key) or {}
        top_hot_keys_status.append(
            {
                "key": key,
                "optimized_v2": True,
                "policy": policy["policy"],
                "cache_seconds": policy["cache_seconds"],
                "live_positions_no_cache": policy["policy"] == "PAPER_POSITION_CACHE_LIVE_FRESH",
                "observed_calls": int(observed.get("count") or 0),
                "observed_bytes": int(observed.get("total_bytes") or 0),
                "avg_bytes_per_call": float(observed.get("avg_payload_bytes") or 0.0),
            }
        )
    largest_avg = _top(keys_by_bytes.values(), limit=1, sort_field="avg_payload_bytes")

    return {
        "ok": True,
        "status": "OK" if not last_error else "DEGRADED",
        "version": VERSION,
        "instrumentation_enabled": instrumentation_enabled(),
        "diet_enabled": bandwidth_diet_enabled(),
        "window": {"started_at": _started_at, "ended_at": _utc_now()},
        "total_ops_observed": total_ops,
        "total_bytes_estimated": total_bytes,
        "bytes_avoided_estimated": bytes_avoided,
        "bytes_avoided_by_cache": cache_bytes_avoided,
        "bytes_avoided_by_set_skipped": set_bytes_avoided,
        "estimated_savings_after_v2_pct": savings_pct,
        "cache_hits": cache_hits,
        "sets_skipped": sets_skipped,
        "top_keys_by_bytes": top_key_rows,
        "top_keys_by_calls": _top(keys_by_bytes.values(), limit=limit, sort_field="count"),
        "top_operations_by_bytes": _top(operations.values(), limit=limit, sort_field="total_bytes"),
        "top_callers_by_bytes": _top(callers.values(), limit=limit, sort_field="total_bytes"),
        "largest_key_by_avg_bytes_per_call": largest_avg[0] if largest_avg else None,
        "largest_payloads": largest,
        "top_hot_keys_status": top_hot_keys_status,
        "temporary_keys_without_ttl": temporary_without_ttl[:limit],
        "old_daily_flags": _old_daily_flags(observed_keys)[:limit],
        "ttl_applied": ttl_applied,
        "recommendations": recommendations,
        "warnings": warnings,
        "instrumentation_errors": errors,
        "last_error": last_error,
        "notes": [
            "Report is built only from in-memory aggregates.",
            "No Redis KEYS, SCAN, GET, or other diagnostic command is issued by this report.",
            "No payload values, credentials, URLs, tokens, registry, lifecycle, order, or position bodies are retained.",
        ],
    }


def build_redis_bandwidth_text(limit: int = DEFAULT_TOP_LIMIT) -> str:
    report = redis_bandwidth_report(limit=limit)
    window = report["window"]
    lines = [
        "REDIS BANDWIDTH DIET V2",
        f"Status: {report['status']}",
        f"Instrumentation: {'ENABLED' if report['instrumentation_enabled'] else 'DISABLED'}",
        f"Diet: {'ENABLED' if report['diet_enabled'] else 'DISABLED'}",
        f"Window: {window['started_at']} -> {window['ended_at']}",
        f"Observed operations: {report['total_ops_observed']}",
        f"Estimated bytes: {report['total_bytes_estimated']}",
        f"Estimated bytes avoided: {report['bytes_avoided_estimated']}",
        f"Bytes avoided by cache: {report['bytes_avoided_by_cache']}",
        f"Bytes avoided by SET skipped: {report['bytes_avoided_by_set_skipped']}",
        f"Estimated savings after V2: {report['estimated_savings_after_v2_pct']}%",
        f"Cache hits: {report['cache_hits']}",
        f"SETs skipped: {report['sets_skipped']}",
        "",
        "Top keys by estimated bytes:",
    ]
    rows = report["top_keys_by_bytes"]
    lines.extend(
        f"{index}. key={row['key']} bytes={row['total_bytes']} calls={row['count']}"
        for index, row in enumerate(rows, 1)
    )
    if not rows:
        lines.append("- no observations")
    largest_avg = report.get("largest_key_by_avg_bytes_per_call")
    lines.extend(["", "Largest key by average bytes/call:"])
    if largest_avg:
        lines.append(
            f"- key={largest_avg['key']} avg_bytes={largest_avg['avg_payload_bytes']} "
            f"calls={largest_avg['count']}"
        )
    else:
        lines.append("- no observations")
    lines.extend(["", "V2 hot key status:"])
    lines.extend(
        f"- key={item['key']} optimized={item['optimized_v2']} policy={item['policy']} "
        f"cache={item['cache_seconds']:g}s live_positions_no_cache={item['live_positions_no_cache']}"
        for item in report["top_hot_keys_status"]
    )
    lines.extend(["", "Top operations by estimated bytes:"])
    rows = report["top_operations_by_bytes"]
    lines.extend(
        f"{index}. op={row['op']} bytes={row['total_bytes']} calls={row['count']}"
        for index, row in enumerate(rows, 1)
    )
    if not rows:
        lines.append("- no observations")
    lines.extend(["", "Top callers by estimated bytes:"])
    rows = report["top_callers_by_bytes"]
    lines.extend(
        f"{index}. caller={row['caller']} bytes={row['total_bytes']} calls={row['count']}"
        for index, row in enumerate(rows, 1)
    )
    if not rows:
        lines.append("- no observations")
    lines.extend(["", "Recommendations:"])
    lines.extend(f"- {item}" for item in report["recommendations"])
    lines.extend(["", "Warnings:"])
    lines.extend(f"- {item}" for item in report["warnings"] or ["none"])
    return "\n".join(lines) + "\n"


def reset_redis_bandwidth_state(confirm: bool = False) -> Dict[str, Any]:
    """Reset in-memory observability/cache state; intended for tests only."""
    global _metrics, _largest_payloads, _cache, _last_values, _ttl_applied
    global _started_at, _cache_hits, _sets_skipped, _bytes_avoided
    global _cache_bytes_avoided, _set_bytes_avoided
    global _instrumentation_errors, _last_error
    if confirm is not True:
        return {"ok": False, "status": "CONFIRM_REQUIRED"}
    with _lock:
        _metrics = {}
        _largest_payloads = deque(maxlen=100)
        _cache = {}
        _last_values = {}
        _ttl_applied = {}
        _started_at = _utc_now()
        _cache_hits = 0
        _sets_skipped = 0
        _bytes_avoided = 0
        _cache_bytes_avoided = 0
        _set_bytes_avoided = 0
        _instrumentation_errors = 0
        _last_error = None
    return {"ok": True, "status": "RESET"}


__all__ = [
    "VERSION",
    "HOT_KEY_POLICIES",
    "HISTORY_HOT_KEY_CACHE_SECONDS",
    "PAPER_POSITION_CACHE_SECONDS",
    "instrumentation_enabled",
    "bandwidth_diet_enabled",
    "sanitize_redis_key",
    "classify_redis_key",
    "safe_cache_seconds_for_key",
    "redis_key_requires_fresh_read",
    "ttl_seconds_for_key",
    "redis_get",
    "redis_set",
    "invalidate_redis_cache",
    "redis_bandwidth_report",
    "build_redis_bandwidth_text",
    "reset_redis_bandwidth_state",
]
