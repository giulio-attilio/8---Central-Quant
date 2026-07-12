"""Passive event-ingestion bridge for Trade Lifecycle Manager V3 Shadow Mode.

The bridge has no operational authority and is disabled by default.  It only
forwards explicitly supplied events; importing it never starts runtime, network
access, workers, or storage.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import trade_lifecycle_manager as _manager


VERSION = "3.1.0-SHADOW-BRIDGE"
SCHEMA_VERSION = 1
TRADE_LIFECYCLE_SHADOW_BRIDGE = True

_lock = threading.RLock()
_counters = {
    "events_received": 0,
    "events_forwarded": 0,
    "events_applied": 0,
    "events_duplicate": 0,
    "events_blocked": 0,
    "events_dead_letter": 0,
    "internal_errors": 0,
}
_last_event_at: Optional[str] = None
_last_success_at: Optional[str] = None
_last_error_at: Optional[str] = None
_last_error: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return default


def _enabled() -> bool:
    return _flag("TRADE_LIFECYCLE_SHADOW_INGESTION_ENABLED", False)


def _persistence_enabled() -> bool:
    return _flag("TRADE_LIFECYCLE_SHADOW_INGESTION_PERSIST", True)


def _dead_letters_enabled() -> bool:
    return _flag("TRADE_LIFECYCLE_SHADOW_DEAD_LETTER_ENABLED", True)


def _data_dir() -> Path:
    configured = os.environ.get("TRADE_LIFECYCLE_SHADOW_DATA_DIR")
    fallback = os.environ.get("CENTRAL_DATA_DIR")
    return Path(configured or fallback or (Path(__file__).resolve().parent / "data"))


def _storage_paths() -> Tuple[Path, Path]:
    base = _data_dir()
    return (
        base / "trade_lifecycle_shadow_ingestion.jsonl",
        base / "trade_lifecycle_shadow_dead_letters.jsonl",
    )


def _safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(_safe(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def _correlation_id(envelope: Mapping[str, Any]) -> str:
    event_id = envelope.get("event_id")
    if event_id:
        material = {
            "event_id": str(event_id),
            "event_type": envelope.get("event_type"),
            "lifecycle_id": envelope.get("lifecycle_id"),
            "source_component": envelope.get("source_component"),
        }
    else:
        material = dict(envelope)
        material.pop("received_at", None)
        material.pop("correlation_id", None)
    return f"CENTRAL-SHADOW-BRIDGE-{_digest(material)[:24]}"


def _base_result(**updates: Any) -> Dict[str, Any]:
    result = {
        "ok": True,
        "status": "",
        "shadow_mode": True,
        "bridge_version": VERSION,
        "operational_impact": False,
        "forwarded": False,
        "lifecycle_id": "",
        "trade_id": "",
        "event_type": "",
        "correlation_id": "",
        "duplicate": False,
        "blocked": False,
        "dead_letter": False,
        "warnings": [],
        "reasons": [],
        "manager_result": {},
    }
    result.update(updates)
    result["operational_impact"] = False
    return result


def _set_error(message: str) -> None:
    global _last_error, _last_error_at
    _last_error = message
    _last_error_at = _now()


def _append(path: Path, record: Mapping[str, Any]) -> Optional[str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_safe(record), ensure_ascii=False) + "\n")
        return None
    except (OSError, TypeError, ValueError) as exc:
        message = f"persistence_error: {exc}"
        _set_error(message)
        return message


def _record_dead_letter(
    reason_code: str,
    reasons: list[str],
    envelope: Mapping[str, Any],
    manager_result: Optional[Mapping[str, Any]],
    *,
    persist: bool,
) -> Dict[str, Any]:
    global _last_error
    recorded_at = _now()
    record = {
        "schema_version": SCHEMA_VERSION,
        "bridge_version": VERSION,
        "shadow_mode": True,
        "dead_letter_id": f"CENTRAL-SHADOW-DEAD-{_digest({'correlation_id': envelope.get('correlation_id'), 'reason_code': reason_code, 'recorded_at': recorded_at})[:24]}",
        "correlation_id": str(envelope.get("correlation_id") or ""),
        "reason_code": reason_code,
        "reasons": list(reasons),
        "envelope": _safe(envelope),
        "manager_result": _safe(manager_result or {}),
        "recorded_at": recorded_at,
        "retry_scheduled": False,
        "operational_impact": False,
    }
    _counters["events_dead_letter"] += 1
    error = None
    persisted = False
    if persist and _dead_letters_enabled():
        error = _append(_storage_paths()[1], record)
        if error:
            _set_error(error)
            _counters["internal_errors"] += 1
        else:
            persisted = True
    return {"record": record, "persisted": persisted, "error": error}


def _journal(envelope: Mapping[str, Any], result: Mapping[str, Any], started: float, *, persist: bool) -> Optional[str]:
    if not persist:
        return None
    completed = _now()
    manager_result = result.get("manager_result") if isinstance(result.get("manager_result"), dict) else {}
    record = {
        "schema_version": SCHEMA_VERSION,
        "bridge_version": VERSION,
        "shadow_mode": True,
        "correlation_id": envelope.get("correlation_id"),
        "event_type": envelope.get("event_type"),
        "lifecycle_id": envelope.get("lifecycle_id"),
        "trade_id": envelope.get("trade_id"),
        "source_component": envelope.get("source_component"),
        "status": result.get("status"),
        "forwarded": bool(result.get("forwarded")),
        "duplicate": bool(result.get("duplicate")),
        "blocked": bool(result.get("blocked")),
        "dead_letter": bool(result.get("dead_letter")),
        "received_at": envelope.get("received_at"),
        "completed_at": completed,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "warnings": list(result.get("warnings") or []),
        "reasons": list(result.get("reasons") or []),
        "manager_status": manager_result.get("status"),
        "operational_impact": False,
    }
    error = _append(_storage_paths()[0], record)
    if error:
        _set_error(error)
        _counters["internal_errors"] += 1
    return error


def _persistence_error_result(
    result: Mapping[str, Any],
    error: str,
    *,
    warning: str,
    reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Expose a Bridge observability failure without undoing Manager state."""
    updated = copy.deepcopy(dict(result))
    updated["ok"] = False
    updated["status"] = "ERROR"
    updated["operational_impact"] = False
    updated.setdefault("reasons", [])
    if "PERSISTENCE_ERROR" not in updated["reasons"]:
        updated["reasons"].append("PERSISTENCE_ERROR")
    updated.setdefault("warnings", [])
    updated["warnings"].append(warning)
    updated["persistence_error"] = error
    if reason_code:
        updated["dead_letter_reason_code"] = reason_code
        updated["retry_scheduled"] = False
    return updated


def _validate_interface(
    event_type: Any,
    lifecycle_id: Any,
    source_component: Any,
    evidence: Any,
    payload: Any,
    persist: Any,
) -> None:
    if not isinstance(event_type, str):
        raise TypeError("event_type must be a string")
    if not isinstance(lifecycle_id, str):
        raise TypeError("lifecycle_id must be a string")
    if not isinstance(source_component, str):
        raise TypeError("source_component must be a string")
    if evidence is not None and not isinstance(evidence, dict):
        raise TypeError("evidence must be a dict or None")
    if payload is not None and not isinstance(payload, dict):
        raise TypeError("payload must be a dict or None")
    if not isinstance(persist, bool):
        raise TypeError("persist must be bool")


def _build_envelope(
    event_type: str,
    lifecycle_id: str,
    source_component: str,
    trade_id: Any,
    event_id: Any,
    occurred_at: Any,
    evidence: Optional[Dict[str, Any]],
    payload: Optional[Dict[str, Any]],
    persist: bool,
) -> Dict[str, Any]:
    received_at = _now()
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "bridge_version": VERSION,
        "shadow_mode": True,
        "correlation_id": "",
        "event_type": event_type.strip().upper(),
        "event_id": None if event_id is None else str(event_id),
        "lifecycle_id": lifecycle_id.strip(),
        "trade_id": None if trade_id is None else str(trade_id),
        "source_component": source_component.strip(),
        "occurred_at": str(occurred_at or received_at),
        "received_at": received_at,
        "evidence": copy.deepcopy(evidence or {}),
        "payload": copy.deepcopy(payload or {}),
        "persist_requested": persist,
        "operational_impact": False,
    }
    envelope["correlation_id"] = _correlation_id(envelope)
    return envelope


def _contract_failure(envelope: Dict[str, Any]) -> Optional[Tuple[str, list[str]]]:
    if not envelope["lifecycle_id"]:
        return "MISSING_LIFECYCLE_ID", ["lifecycle_id is required"]
    if not envelope["source_component"]:
        return "MISSING_SOURCE_COMPONENT", ["source_component is required"]
    canonical = {item.value for item in _manager.LifecycleEvent}
    if envelope["event_type"] not in canonical:
        return "INVALID_EVENT_TYPE", ["event_type is not canonical"]
    return None


def _disabled_result(event_type: str = "", lifecycle_id: str = "", trade_id: Any = None) -> Dict[str, Any]:
    return _base_result(
        status="DISABLED",
        forwarded=False,
        lifecycle_id=lifecycle_id.strip(),
        trade_id=str(trade_id or ""),
        event_type=event_type.strip().upper(),
    )


def emit_shadow_event(
    event_type: str,
    *,
    lifecycle_id: str,
    source_component: str,
    trade_id: Optional[str] = None,
    event_id: Optional[str] = None,
    occurred_at: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Forward one explicitly supplied event without operational side effects."""
    global _last_event_at, _last_success_at
    _validate_interface(event_type, lifecycle_id, source_component, evidence, payload, persist)
    if not _enabled():
        return _disabled_result(event_type, lifecycle_id, trade_id)

    started = time.perf_counter()
    envelope = _build_envelope(event_type, lifecycle_id, source_component, trade_id, event_id, occurred_at, evidence, payload, persist)
    effective_persist = persist and _persistence_enabled()
    with _lock:
        _counters["events_received"] += 1
        _last_event_at = envelope["received_at"]
        failure = _contract_failure(envelope)
        if failure:
            reason_code, reasons = failure
            dead_letter_result = _record_dead_letter(reason_code, reasons, envelope, {}, persist=effective_persist)
            result = _base_result(
                ok=False, status="DEAD_LETTER", lifecycle_id=envelope["lifecycle_id"],
                trade_id=str(envelope["trade_id"] or ""), event_type=envelope["event_type"],
                correlation_id=envelope["correlation_id"], dead_letter=True, reasons=reasons,
                dead_letter_reason_code=reason_code, retry_scheduled=False,
            )
            if dead_letter_result["error"]:
                result = _persistence_error_result(
                    result, dead_letter_result["error"],
                    warning="Dead letter was classified but its Bridge journal write failed.",
                    reason_code=reason_code,
                )
            journal_error = _journal(envelope, result, started, persist=effective_persist)
            if journal_error:
                result = _persistence_error_result(
                    result, journal_error,
                    warning="The attempt was processed, but the Bridge ingestion journal write failed.",
                )
            return result

        manager_event = {
            "event_type": envelope["event_type"],
            "event_id": envelope["event_id"],
            "lifecycle_id": envelope["lifecycle_id"],
            "source_component": envelope["source_component"],
            "occurred_at": envelope["occurred_at"],
            "received_at": envelope["received_at"],
            "evidence": copy.deepcopy(envelope["evidence"]),
            "payload": copy.deepcopy(envelope["payload"]),
        }
        if envelope["trade_id"] is not None:
            manager_event["trade_id"] = envelope["trade_id"]
        try:
            _counters["events_forwarded"] += 1
            manager_result = _manager.apply_event(envelope["lifecycle_id"], manager_event, persist=effective_persist)
            manager_status = str(manager_result.get("status") or "")
            if manager_status == "LIFECYCLE_NOT_FOUND":
                status, reason_code = "DEAD_LETTER", "LIFECYCLE_NOT_FOUND"
            elif manager_result.get("duplicate"):
                status, reason_code = "DUPLICATE", ""
                _counters["events_duplicate"] += 1
            elif manager_result.get("blocked"):
                status, reason_code = "BLOCKED", "TRANSITION_BLOCKED"
                _counters["events_blocked"] += 1
            elif manager_result.get("event_applied"):
                status, reason_code = "APPLIED", ""
                _counters["events_applied"] += 1
                _last_success_at = _now()
            else:
                status, reason_code = "ERROR", "MANAGER_ERROR"
                message = f"unexpected_manager_result: {manager_result!r}"
                _set_error(message)
                _counters["internal_errors"] += 1

            dead_letter = bool(reason_code and status in {"BLOCKED", "DEAD_LETTER", "ERROR"})
            reasons = list(manager_result.get("reasons") or [])
            if status == "ERROR" and not reasons:
                reasons = [message]
            dead_letter_result = None
            if dead_letter:
                dead_letter_result = _record_dead_letter(reason_code, reasons or [manager_status or reason_code], envelope, manager_result, persist=effective_persist)
            result = _base_result(
                ok=status in {"APPLIED", "DUPLICATE"}, status=status, forwarded=True,
                lifecycle_id=envelope["lifecycle_id"], trade_id=str(manager_result.get("trade_id") or envelope["trade_id"] or ""),
                event_type=envelope["event_type"], correlation_id=envelope["correlation_id"],
                duplicate=bool(manager_result.get("duplicate")), blocked=bool(manager_result.get("blocked")),
                dead_letter=dead_letter, warnings=list(manager_result.get("warnings") or []), reasons=reasons,
                manager_result=_safe(manager_result),
            )
            if dead_letter:
                result["dead_letter_reason_code"] = reason_code
                result["retry_scheduled"] = False
            if dead_letter_result and dead_letter_result["error"]:
                result = _persistence_error_result(
                    result, dead_letter_result["error"],
                    warning="Dead letter was classified but its Bridge journal write failed.",
                    reason_code=reason_code,
                )
        except Exception as exc:  # defensive boundary for a future operational caller
            message = f"manager_error: {type(exc).__name__}: {exc}"
            _set_error(message)
            _counters["internal_errors"] += 1
            dead_letter_result = _record_dead_letter("MANAGER_ERROR", [message], envelope, {}, persist=effective_persist)
            result = _base_result(
                ok=False, status="ERROR", forwarded=True, lifecycle_id=envelope["lifecycle_id"],
                trade_id=str(envelope["trade_id"] or ""), event_type=envelope["event_type"],
                correlation_id=envelope["correlation_id"], dead_letter=True, reasons=[message],
                dead_letter_reason_code="MANAGER_ERROR", retry_scheduled=False,
            )
            if dead_letter_result["error"]:
                result = _persistence_error_result(
                    result, dead_letter_result["error"],
                    warning="Dead letter was classified but its Bridge journal write failed.",
                    reason_code="MANAGER_ERROR",
                )
        journal_error = _journal(envelope, result, started, persist=effective_persist)
        if journal_error:
            result = _persistence_error_result(
                result, journal_error,
                warning="The fact may have been processed by the Manager, but the Bridge ingestion journal write failed.",
            )
        return result


def emit_shadow_lifecycle_created(
    lifecycle_payload: Dict[str, Any],
    *,
    source_component: str,
    persist: bool = True,
) -> Dict[str, Any]:
    """Explicitly request creation of one shadow lifecycle."""
    global _last_event_at, _last_success_at
    if not isinstance(lifecycle_payload, dict):
        raise TypeError("lifecycle_payload must be a dict")
    if not isinstance(source_component, str):
        raise TypeError("source_component must be a string")
    if not isinstance(persist, bool):
        raise TypeError("persist must be bool")
    payload_copy = copy.deepcopy(lifecycle_payload)
    if not _enabled():
        return _disabled_result("SIGNAL_CREATED", str(payload_copy.get("lifecycle_id") or ""), payload_copy.get("trade_id"))

    started = time.perf_counter()
    envelope = _build_envelope(
        "SIGNAL_CREATED", str(payload_copy.get("lifecycle_id") or ""), source_component,
        payload_copy.get("trade_id"), payload_copy.get("event_id"), payload_copy.get("occurred_at"),
        payload_copy.get("evidence") if isinstance(payload_copy.get("evidence"), dict) else {}, payload_copy, persist,
    )
    effective_persist = persist and _persistence_enabled()
    with _lock:
        _counters["events_received"] += 1
        _last_event_at = envelope["received_at"]
        reasons = []
        reason_code = ""
        if not envelope["lifecycle_id"]:
            reason_code, reasons = "MISSING_LIFECYCLE_ID", ["lifecycle_id is required"]
        elif not envelope["source_component"]:
            reason_code, reasons = "MISSING_SOURCE_COMPONENT", ["source_component is required"]
        elif not (payload_copy.get("external_position") or payload_copy.get("manual_position")) and not payload_copy.get("trade_id"):
            reason_code, reasons = "CREATE_BLOCKED", ["trade_id is required for operational lifecycles"]
        if reason_code:
            dead_letter_result = _record_dead_letter(reason_code, reasons, envelope, {}, persist=effective_persist)
            result = _base_result(
                ok=False, status="DEAD_LETTER", lifecycle_id=envelope["lifecycle_id"],
                trade_id=str(envelope["trade_id"] or ""), event_type="SIGNAL_CREATED",
                correlation_id=envelope["correlation_id"], dead_letter=True, reasons=reasons,
                dead_letter_reason_code=reason_code, retry_scheduled=False,
            )
            if dead_letter_result["error"]:
                result = _persistence_error_result(
                    result, dead_letter_result["error"],
                    warning="Dead letter was classified but its Bridge journal write failed.",
                    reason_code=reason_code,
                )
            journal_error = _journal(envelope, result, started, persist=effective_persist)
            if journal_error:
                result = _persistence_error_result(
                    result, journal_error,
                    warning="The attempt was processed, but the Bridge ingestion journal write failed.",
                )
            return result
        try:
            _counters["events_forwarded"] += 1
            manager_result = _manager.create_lifecycle(payload_copy, persist=effective_persist)
            dead_letter_result = None
            if manager_result.get("duplicate"):
                status = "DUPLICATE"
                _counters["events_duplicate"] += 1
            elif manager_result.get("blocked"):
                status = "DEAD_LETTER"
                _counters["events_blocked"] += 1
                dead_letter_result = _record_dead_letter("CREATE_BLOCKED", list(manager_result.get("reasons") or []), envelope, manager_result, persist=effective_persist)
            elif manager_result.get("ok"):
                status = "LIFECYCLE_CREATED"
                _counters["events_applied"] += 1
                _last_success_at = _now()
            else:
                status = "ERROR"
                message = f"unexpected_manager_result: {manager_result!r}"
                _set_error(message)
                _counters["internal_errors"] += 1
                dead_letter_result = _record_dead_letter("MANAGER_ERROR", [message], envelope, manager_result, persist=effective_persist)
            result = _base_result(
                ok=status in {"LIFECYCLE_CREATED", "DUPLICATE"}, status=status, forwarded=True,
                lifecycle_id=envelope["lifecycle_id"], trade_id=str(manager_result.get("trade_id") or envelope["trade_id"] or ""),
                event_type="SIGNAL_CREATED", correlation_id=envelope["correlation_id"],
                duplicate=status == "DUPLICATE", blocked=bool(manager_result.get("blocked")),
                dead_letter=status == "DEAD_LETTER", warnings=list(manager_result.get("warnings") or []),
                reasons=list(manager_result.get("reasons") or []), manager_result=_safe(manager_result),
            )
            if dead_letter_result:
                reason_code = "CREATE_BLOCKED" if status == "DEAD_LETTER" else "MANAGER_ERROR"
                result["dead_letter"] = True
                result["dead_letter_reason_code"] = reason_code
                result["retry_scheduled"] = False
                if status == "ERROR" and not result["reasons"]:
                    result["reasons"] = [message]
                if dead_letter_result["error"]:
                    result = _persistence_error_result(
                        result, dead_letter_result["error"],
                        warning="Dead letter was classified but its Bridge journal write failed.",
                        reason_code=reason_code,
                    )
        except Exception as exc:  # defensive boundary for a future operational caller
            message = f"manager_error: {type(exc).__name__}: {exc}"
            _set_error(message)
            _counters["internal_errors"] += 1
            dead_letter_result = _record_dead_letter("MANAGER_ERROR", [message], envelope, {}, persist=effective_persist)
            result = _base_result(
                ok=False, status="ERROR", forwarded=True, lifecycle_id=envelope["lifecycle_id"],
                trade_id=str(envelope["trade_id"] or ""), event_type="SIGNAL_CREATED",
                correlation_id=envelope["correlation_id"], dead_letter=True, reasons=[message],
                dead_letter_reason_code="MANAGER_ERROR", retry_scheduled=False,
            )
            if dead_letter_result["error"]:
                result = _persistence_error_result(
                    result, dead_letter_result["error"],
                    warning="Dead letter was classified but its Bridge journal write failed.",
                    reason_code="MANAGER_ERROR",
                )
        journal_error = _journal(envelope, result, started, persist=effective_persist)
        if journal_error:
            result = _persistence_error_result(
                result, journal_error,
                warning="The fact may have been processed by the Manager, but the Bridge ingestion journal write failed.",
            )
        return result


def _read_jsonl(path: Path, limit: int) -> Dict[str, Any]:
    if not isinstance(limit, int) or limit < 0:
        raise TypeError("limit must be a non-negative int")
    if limit == 0 or not path.exists():
        return {"ok": True, "shadow_mode": True, "count": 0, "invalid_lines": 0, "items": []}
    items = []
    invalid = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    items.append(item)
                else:
                    invalid += 1
            except (TypeError, ValueError, json.JSONDecodeError):
                invalid += 1
    except OSError as exc:
        _set_error(f"journal_read_error: {exc}")
        return {"ok": False, "shadow_mode": True, "count": 0, "invalid_lines": 0, "items": [], "error": str(exc)}
    selected = items[-limit:]
    return {"ok": True, "shadow_mode": True, "count": len(selected), "invalid_lines": invalid, "items": _safe(selected)}


def read_shadow_ingestion_log(limit: int = 100) -> Dict[str, Any]:
    return _read_jsonl(_storage_paths()[0], limit)


def read_shadow_dead_letters(limit: int = 100) -> Dict[str, Any]:
    return _read_jsonl(_storage_paths()[1], limit)


def shadow_bridge_health() -> Dict[str, Any]:
    ingestion, dead_letters = _storage_paths()
    try:
        manager_health = _safe(_manager.trade_lifecycle_health())
    except Exception as exc:  # health must remain available if the manager fails
        manager_health = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    with _lock:
        return {
            "ok": _last_error is None,
            "version": VERSION,
            "shadow_mode": True,
            "enabled": _enabled(),
            "loaded": True,
            "operational_impact": False,
            **dict(_counters),
            "last_event_at": _last_event_at,
            "last_success_at": _last_success_at,
            "last_error_at": _last_error_at,
            "last_error": _last_error,
            "storage_paths": {"ingestion": str(ingestion), "dead_letters": str(dead_letters)},
            "lifecycle_manager": manager_health,
            "notes": [
                "No operational authority.",
                "Does not block execution or alter the Trade Registry.",
                "Does not call Broker or exchange.",
                "Not integrated into runtime.",
            ],
        }


def reset_shadow_bridge_storage(confirm: bool = False) -> Dict[str, Any]:
    global _last_event_at, _last_success_at, _last_error_at, _last_error
    if not isinstance(confirm, bool):
        raise TypeError("confirm must be bool")
    if not confirm:
        return {"ok": False, "status": "CONFIRM_REQUIRED", "reset": False, "shadow_mode": True, "operational_impact": False}
    errors = []
    with _lock:
        for path in _storage_paths():
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        for key in _counters:
            _counters[key] = 0
        _last_event_at = None
        _last_success_at = None
        _last_error_at = None
        _last_error = None
    return {
        "ok": not errors,
        "status": "RESET" if not errors else "RESET_PARTIAL",
        "reset": True,
        "shadow_mode": True,
        "operational_impact": False,
        "errors": errors,
    }


__all__ = [
    "VERSION",
    "TRADE_LIFECYCLE_SHADOW_BRIDGE",
    "emit_shadow_event",
    "emit_shadow_lifecycle_created",
    "shadow_bridge_health",
    "read_shadow_ingestion_log",
    "read_shadow_dead_letters",
    "reset_shadow_bridge_storage",
]
