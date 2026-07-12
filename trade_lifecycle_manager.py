"""Trade Lifecycle Manager V3.0 — passive, isolated Shadow Mode.

This module reconstructs lifecycle state from explicitly supplied events.  It has
no operational authority: it never imports or calls the broker, exchange, current
registry, bots, runtime, network, Redis, or messaging services.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


TRADE_LIFECYCLE_SHADOW_MODE = True
VERSION = "3.0.0-SHADOW"
SCHEMA_VERSION = 1
QUANTITY_TOLERANCE = 1e-9


class LifecycleState(str, Enum):
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    DECISION_PENDING = "DECISION_PENDING"
    DECISION_ALLOWED = "DECISION_ALLOWED"
    DECISION_DENIED = "DECISION_DENIED"
    RISK_PENDING = "RISK_PENDING"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_DENIED = "RISK_DENIED"
    ENTRY_INTENT_RECORDED = "ENTRY_INTENT_RECORDED"
    ENTRY_SUBMITTING = "ENTRY_SUBMITTING"
    ENTRY_SUBMISSION_UNKNOWN = "ENTRY_SUBMISSION_UNKNOWN"
    ENTRY_REJECTED_CONFIRMED = "ENTRY_REJECTED_CONFIRMED"
    ENTRY_PARTIALLY_FILLED = "ENTRY_PARTIALLY_FILLED"
    ENTRY_CONFIRMED = "ENTRY_CONFIRMED"
    ENTRY_CONFIRMED_STOP_MISSING = "ENTRY_CONFIRMED_STOP_MISSING"
    ENTRY_PROTECTED = "ENTRY_PROTECTED"
    POSITION_MANAGED = "POSITION_MANAGED"
    TP50_PENDING = "TP50_PENDING"
    TP50_CONFIRMED = "TP50_CONFIRMED"
    RUNNER_PROTECTED = "RUNNER_PROTECTED"
    BREAK_EVEN_PENDING = "BREAK_EVEN_PENDING"
    BREAK_EVEN_ACTIVE = "BREAK_EVEN_ACTIVE"
    TRAILING_PENDING = "TRAILING_PENDING"
    TRAILING_ACTIVE = "TRAILING_ACTIVE"
    CLOSE_PENDING = "CLOSE_PENDING"
    CLOSE_PARTIALLY_CONFIRMED = "CLOSE_PARTIALLY_CONFIRMED"
    CLOSE_CONFIRMED = "CLOSE_CONFIRMED"
    OUTCOME_PENDING = "OUTCOME_PENDING"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    LEARNING_ELIGIBLE = "LEARNING_ELIGIBLE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    MANUAL_POSITION_DETECTED = "MANUAL_POSITION_DETECTED"
    EXTERNAL_EXPOSURE_ONLY = "EXTERNAL_EXPOSURE_ONLY"


class LifecycleEvent(str, Enum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    DECISION_PENDING_RECORDED = "DECISION_PENDING_RECORDED"
    DECISION_ALLOWED_RECORDED = "DECISION_ALLOWED_RECORDED"
    DECISION_DENIED_RECORDED = "DECISION_DENIED_RECORDED"
    RISK_PENDING_RECORDED = "RISK_PENDING_RECORDED"
    RISK_APPROVED_RECORDED = "RISK_APPROVED_RECORDED"
    RISK_DENIED_RECORDED = "RISK_DENIED_RECORDED"
    ENTRY_INTENT_CREATED = "ENTRY_INTENT_CREATED"
    ENTRY_SUBMITTED = "ENTRY_SUBMITTED"
    ENTRY_SUBMISSION_BECAME_UNKNOWN = "ENTRY_SUBMISSION_BECAME_UNKNOWN"
    ENTRY_REJECTED = "ENTRY_REJECTED"
    ENTRY_FILL_RECORDED = "ENTRY_FILL_RECORDED"
    ENTRY_PARTIAL_RECORDED = "ENTRY_PARTIAL_RECORDED"
    ENTRY_CONFIRMED = "ENTRY_CONFIRMED"
    DISASTER_STOP_REQUESTED = "DISASTER_STOP_REQUESTED"
    DISASTER_STOP_CONFIRMED = "DISASTER_STOP_CONFIRMED"
    DISASTER_STOP_FAILED = "DISASTER_STOP_FAILED"
    POSITION_MANAGEMENT_STARTED = "POSITION_MANAGEMENT_STARTED"
    TP50_REQUESTED = "TP50_REQUESTED"
    TP50_FILL_RECORDED = "TP50_FILL_RECORDED"
    TP50_CONFIRMED = "TP50_CONFIRMED"
    RUNNER_PROTECTION_CONFIRMED = "RUNNER_PROTECTION_CONFIRMED"
    BREAK_EVEN_REQUESTED = "BREAK_EVEN_REQUESTED"
    BREAK_EVEN_CONFIRMED = "BREAK_EVEN_CONFIRMED"
    TRAILING_REQUESTED = "TRAILING_REQUESTED"
    TRAILING_CONFIRMED = "TRAILING_CONFIRMED"
    CLOSE_REQUESTED = "CLOSE_REQUESTED"
    CLOSE_FILL_RECORDED = "CLOSE_FILL_RECORDED"
    CLOSE_PARTIAL_RECORDED = "CLOSE_PARTIAL_RECORDED"
    CLOSE_CONFIRMED = "CLOSE_CONFIRMED"
    OUTCOME_REQUESTED = "OUTCOME_REQUESTED"
    OUTCOME_CREATED = "OUTCOME_CREATED"
    OUTCOME_CONFIRMED = "OUTCOME_CONFIRMED"
    LEARNING_ELIGIBILITY_CONFIRMED = "LEARNING_ELIGIBILITY_CONFIRMED"
    RECONCILIATION_REQUESTED = "RECONCILIATION_REQUESTED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    RECOVERY_REQUESTED = "RECOVERY_REQUESTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    EXTERNAL_POSITION_DETECTED = "EXTERNAL_POSITION_DETECTED"
    EXTERNAL_POSITION_CLASSIFIED = "EXTERNAL_POSITION_CLASSIFIED"


DYNAMIC = "__DYNAMIC__"
TRANSITION_MATRIX: Dict[str, Dict[str, str]] = {
    LifecycleState.SIGNAL_DETECTED.value: {
        LifecycleEvent.DECISION_PENDING_RECORDED.value: LifecycleState.DECISION_PENDING.value,
    },
    LifecycleState.DECISION_PENDING.value: {
        LifecycleEvent.DECISION_ALLOWED_RECORDED.value: LifecycleState.DECISION_ALLOWED.value,
        LifecycleEvent.DECISION_DENIED_RECORDED.value: LifecycleState.DECISION_DENIED.value,
    },
    LifecycleState.DECISION_ALLOWED.value: {
        LifecycleEvent.RISK_PENDING_RECORDED.value: LifecycleState.RISK_PENDING.value,
    },
    LifecycleState.RISK_PENDING.value: {
        LifecycleEvent.RISK_APPROVED_RECORDED.value: LifecycleState.RISK_APPROVED.value,
        LifecycleEvent.RISK_DENIED_RECORDED.value: LifecycleState.RISK_DENIED.value,
    },
    LifecycleState.RISK_APPROVED.value: {
        LifecycleEvent.ENTRY_INTENT_CREATED.value: LifecycleState.ENTRY_INTENT_RECORDED.value,
    },
    LifecycleState.ENTRY_INTENT_RECORDED.value: {
        LifecycleEvent.ENTRY_SUBMITTED.value: LifecycleState.ENTRY_SUBMITTING.value,
    },
    LifecycleState.ENTRY_SUBMITTING.value: {
        LifecycleEvent.ENTRY_SUBMISSION_BECAME_UNKNOWN.value: LifecycleState.ENTRY_SUBMISSION_UNKNOWN.value,
        LifecycleEvent.ENTRY_REJECTED.value: LifecycleState.ENTRY_REJECTED_CONFIRMED.value,
        LifecycleEvent.ENTRY_FILL_RECORDED.value: DYNAMIC,
        LifecycleEvent.ENTRY_PARTIAL_RECORDED.value: LifecycleState.ENTRY_PARTIALLY_FILLED.value,
        LifecycleEvent.ENTRY_CONFIRMED.value: LifecycleState.ENTRY_CONFIRMED.value,
    },
    LifecycleState.ENTRY_SUBMISSION_UNKNOWN.value: {
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
    },
    LifecycleState.ENTRY_PARTIALLY_FILLED.value: {
        LifecycleEvent.ENTRY_FILL_RECORDED.value: DYNAMIC,
        LifecycleEvent.ENTRY_CONFIRMED.value: LifecycleState.ENTRY_CONFIRMED.value,
        LifecycleEvent.DISASTER_STOP_REQUESTED.value: LifecycleState.ENTRY_CONFIRMED_STOP_MISSING.value,
        LifecycleEvent.DISASTER_STOP_CONFIRMED.value: LifecycleState.ENTRY_PROTECTED.value,
        LifecycleEvent.DISASTER_STOP_FAILED.value: LifecycleState.ENTRY_CONFIRMED_STOP_MISSING.value,
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
    },
    LifecycleState.ENTRY_CONFIRMED.value: {
        LifecycleEvent.DISASTER_STOP_REQUESTED.value: LifecycleState.ENTRY_CONFIRMED_STOP_MISSING.value,
        LifecycleEvent.DISASTER_STOP_CONFIRMED.value: LifecycleState.ENTRY_PROTECTED.value,
        LifecycleEvent.DISASTER_STOP_FAILED.value: LifecycleState.ENTRY_CONFIRMED_STOP_MISSING.value,
        LifecycleEvent.RECOVERY_REQUESTED.value: LifecycleState.RECOVERY_REQUIRED.value,
    },
    LifecycleState.ENTRY_CONFIRMED_STOP_MISSING.value: {
        LifecycleEvent.DISASTER_STOP_CONFIRMED.value: LifecycleState.ENTRY_PROTECTED.value,
        LifecycleEvent.RECOVERY_REQUESTED.value: LifecycleState.RECOVERY_REQUIRED.value,
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
    },
    LifecycleState.ENTRY_PROTECTED.value: {
        LifecycleEvent.POSITION_MANAGEMENT_STARTED.value: LifecycleState.POSITION_MANAGED.value,
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
    },
    LifecycleState.POSITION_MANAGED.value: {
        LifecycleEvent.TP50_REQUESTED.value: LifecycleState.TP50_PENDING.value,
        LifecycleEvent.BREAK_EVEN_REQUESTED.value: LifecycleState.BREAK_EVEN_PENDING.value,
        LifecycleEvent.TRAILING_REQUESTED.value: LifecycleState.TRAILING_PENDING.value,
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
    },
    LifecycleState.TP50_PENDING.value: {
        LifecycleEvent.TP50_FILL_RECORDED.value: LifecycleState.TP50_PENDING.value,
        LifecycleEvent.TP50_CONFIRMED.value: LifecycleState.TP50_CONFIRMED.value,
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
    },
    LifecycleState.TP50_CONFIRMED.value: {
        LifecycleEvent.RUNNER_PROTECTION_CONFIRMED.value: LifecycleState.RUNNER_PROTECTED.value,
        LifecycleEvent.RECOVERY_REQUESTED.value: LifecycleState.RECOVERY_REQUIRED.value,
    },
    LifecycleState.RUNNER_PROTECTED.value: {
        LifecycleEvent.BREAK_EVEN_REQUESTED.value: LifecycleState.BREAK_EVEN_PENDING.value,
        LifecycleEvent.TRAILING_REQUESTED.value: LifecycleState.TRAILING_PENDING.value,
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
    },
    LifecycleState.BREAK_EVEN_PENDING.value: {
        LifecycleEvent.BREAK_EVEN_CONFIRMED.value: LifecycleState.BREAK_EVEN_ACTIVE.value,
        LifecycleEvent.RECOVERY_REQUESTED.value: LifecycleState.RECOVERY_REQUIRED.value,
    },
    LifecycleState.BREAK_EVEN_ACTIVE.value: {
        LifecycleEvent.TRAILING_REQUESTED.value: LifecycleState.TRAILING_PENDING.value,
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
        LifecycleEvent.BREAK_EVEN_REQUESTED.value: LifecycleState.BREAK_EVEN_PENDING.value,
    },
    LifecycleState.TRAILING_PENDING.value: {
        LifecycleEvent.TRAILING_CONFIRMED.value: LifecycleState.TRAILING_ACTIVE.value,
        LifecycleEvent.RECOVERY_REQUESTED.value: LifecycleState.RECOVERY_REQUIRED.value,
    },
    LifecycleState.TRAILING_ACTIVE.value: {
        LifecycleEvent.TRAILING_REQUESTED.value: LifecycleState.TRAILING_PENDING.value,
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
    },
    LifecycleState.CLOSE_PENDING.value: {
        LifecycleEvent.CLOSE_FILL_RECORDED.value: DYNAMIC,
        LifecycleEvent.CLOSE_PARTIAL_RECORDED.value: LifecycleState.CLOSE_PARTIALLY_CONFIRMED.value,
        LifecycleEvent.CLOSE_CONFIRMED.value: LifecycleState.CLOSE_CONFIRMED.value,
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
    },
    LifecycleState.CLOSE_PARTIALLY_CONFIRMED.value: {
        LifecycleEvent.CLOSE_REQUESTED.value: LifecycleState.CLOSE_PENDING.value,
        LifecycleEvent.CLOSE_FILL_RECORDED.value: DYNAMIC,
        LifecycleEvent.CLOSE_CONFIRMED.value: LifecycleState.CLOSE_CONFIRMED.value,
        LifecycleEvent.RUNNER_PROTECTION_CONFIRMED.value: LifecycleState.RUNNER_PROTECTED.value,
    },
    LifecycleState.CLOSE_CONFIRMED.value: {
        LifecycleEvent.OUTCOME_REQUESTED.value: LifecycleState.OUTCOME_PENDING.value,
        LifecycleEvent.OUTCOME_CREATED.value: LifecycleState.OUTCOME_PENDING.value,
    },
    LifecycleState.OUTCOME_PENDING.value: {
        LifecycleEvent.OUTCOME_CREATED.value: LifecycleState.OUTCOME_PENDING.value,
        LifecycleEvent.OUTCOME_CONFIRMED.value: LifecycleState.OUTCOME_RECORDED.value,
    },
    LifecycleState.OUTCOME_RECORDED.value: {
        LifecycleEvent.LEARNING_ELIGIBILITY_CONFIRMED.value: LifecycleState.LEARNING_ELIGIBLE.value,
    },
    LifecycleState.RECONCILIATION_REQUIRED.value: {
        LifecycleEvent.RECONCILIATION_COMPLETED.value: DYNAMIC,
        LifecycleEvent.RECOVERY_REQUESTED.value: LifecycleState.RECOVERY_REQUIRED.value,
    },
    LifecycleState.RECOVERY_REQUIRED.value: {
        LifecycleEvent.RECOVERY_COMPLETED.value: DYNAMIC,
        LifecycleEvent.RECONCILIATION_REQUESTED.value: LifecycleState.RECONCILIATION_REQUIRED.value,
        LifecycleEvent.DISASTER_STOP_CONFIRMED.value: LifecycleState.ENTRY_PROTECTED.value,
    },
    LifecycleState.MANUAL_POSITION_DETECTED.value: {
        LifecycleEvent.EXTERNAL_POSITION_CLASSIFIED.value: LifecycleState.EXTERNAL_EXPOSURE_ONLY.value,
    },
}


_lock = threading.RLock()
_lifecycles: Dict[str, Dict[str, Any]] = {}
_event_count = 0
_divergence_count = 0
_loaded = False
_last_error: Optional[str] = None


def _resolve_data_dir() -> Path:
    configured = os.environ.get("TRADE_LIFECYCLE_SHADOW_DATA_DIR")
    fallback = os.environ.get("CENTRAL_DATA_DIR")
    return Path(configured or fallback or (Path(__file__).resolve().parent / "data"))


DATA_DIR = _resolve_data_dir()
SNAPSHOT_FILE = DATA_DIR / "trade_lifecycle_shadow_snapshot.json"
EVENTS_FILE = DATA_DIR / "trade_lifecycle_shadow_events.jsonl"
DIVERGENCES_FILE = DATA_DIR / "trade_lifecycle_shadow_divergences.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError) as exc:
        raise TypeError(f"value is not JSON serializable: {exc}") from exc


def _deepcopy(value: Any) -> Any:
    return copy.deepcopy(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number


def _normalize_mode(value: Any) -> str:
    mode = str(value or "UNKNOWN").upper().strip()
    aliases = {"REAL": "LIVE", "DRY_RUN": "VERIFY", "OBSERVATION_ONLY": "VERIFY"}
    mode = aliases.get(mode, mode)
    return mode if mode in {"PAPER", "VERIFY", "LIVE", "UNKNOWN"} else "UNKNOWN"


def _normalize_side(value: Any) -> str:
    side = str(value or "").upper().strip()
    if side in {"BUY", "LONG"}:
        return "LONG"
    if side in {"SELL", "SHORT"}:
        return "SHORT"
    return side


def _ensure_loaded() -> None:
    global _loaded, _last_error, _lifecycles, _event_count, _divergence_count
    with _lock:
        if _loaded:
            return
        _loaded = True
        if not SNAPSHOT_FILE.exists():
            return
        try:
            data = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("unsupported or invalid snapshot schema")
            records = data.get("lifecycles")
            if not isinstance(records, dict):
                raise ValueError("snapshot lifecycles must be a mapping")
            _lifecycles = records
            _event_count = int(data.get("event_count") or 0)
            _divergence_count = int(data.get("divergence_count") or 0)
            _last_error = None
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            _last_error = f"snapshot_load_error: {exc}"


def _ensure_storage_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_snapshot() -> None:
    _ensure_storage_dir()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "manager_version": VERSION,
        "shadow_mode": True,
        "updated_at": _now(),
        "event_count": _event_count,
        "divergence_count": _divergence_count,
        "lifecycles": _lifecycles,
    }
    temp = SNAPSHOT_FILE.with_suffix(SNAPSHOT_FILE.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, SNAPSHOT_FILE)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    _ensure_storage_dir()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _persist_all() -> Optional[str]:
    global _last_error
    try:
        _atomic_write_snapshot()
        _last_error = None
        return None
    except OSError as exc:
        _last_error = f"snapshot_write_error: {exc}"
        return _last_error


def _result(
    snapshot: Optional[Dict[str, Any]],
    *,
    ok: bool,
    status: str,
    previous_state: str = "",
    current_state: str = "",
    event_applied: bool = False,
    duplicate: bool = False,
    blocked: bool = False,
    reasons: Optional[Iterable[str]] = None,
    warnings: Optional[Iterable[str]] = None,
    divergences: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    snap = _deepcopy(snapshot or {})
    return {
        "ok": bool(ok),
        "status": status,
        "shadow_mode": True,
        "lifecycle_id": str(snap.get("lifecycle_id") or ""),
        "trade_id": str(snap.get("trade_id") or ""),
        "previous_state": previous_state,
        "current_state": current_state or str(snap.get("state") or ""),
        "event_applied": bool(event_applied),
        "duplicate": bool(duplicate),
        "blocked": bool(blocked),
        "reasons": list(reasons or []),
        "warnings": list(warnings or []),
        "divergences": _deepcopy(list(divergences or [])),
        "snapshot": snap,
    }


def _new_snapshot(payload: Mapping[str, Any], state: str) -> Dict[str, Any]:
    now = _now()
    external = state == LifecycleState.MANUAL_POSITION_DETECTED.value
    trade_id = "" if external else str(payload.get("trade_id") or "")
    return {
        "schema_version": SCHEMA_VERSION,
        "manager_version": VERSION,
        "shadow_mode": True,
        "trade_id": trade_id,
        "lifecycle_id": str(payload.get("lifecycle_id") or ""),
        "signal_id": "" if external else str(payload.get("signal_id") or ""),
        "decision_id": "" if external else str(payload.get("decision_id") or ""),
        "client_order_id": None,
        "exchange_order_id": None,
        "fill_ids": [],
        "outcome_id": None,
        "bot": "" if external else str(payload.get("bot") or ""),
        "setup": "" if external else str(payload.get("setup") or ""),
        "symbol": str(payload.get("symbol") or "").upper().strip(),
        "side": _normalize_side(payload.get("side")),
        "mode": _normalize_mode(payload.get("mode")),
        "state": state,
        "quantity_planned": max(0.0, _safe_float(payload.get("quantity_planned"))),
        "quantity_filled": 0.0,
        "quantity_open": 0.0,
        "quantity_closed": 0.0,
        "entry_price_theoretical": payload.get("entry_price_theoretical"),
        "entry_price_confirmed": None,
        "disaster_stop": {},
        "tp50": {},
        "runner": {},
        "break_even": {},
        "trailing": {},
        "close": {},
        "reconciliation": {},
        "recovery": {},
        "outcome": {},
        "warnings": [],
        "divergences": [],
        "history": [],
        "events_applied": [],
        "event_keys": [],
        "blocked_event_keys": [],
        "external_position": _json_safe(payload) if external else {},
        "created_at": now,
        "updated_at": now,
        "revision": 0,
    }


def _record_divergence(snapshot: Dict[str, Any], field: str, shadow_value: Any, other_value: Any, severity: str, reason: str, persist: bool) -> Dict[str, Any]:
    global _divergence_count
    item = {
        "lifecycle_id": snapshot.get("lifecycle_id"),
        "trade_id": snapshot.get("trade_id"),
        "field": field,
        "shadow_value": _json_safe(shadow_value),
        "registry_value": _json_safe(other_value),
        "severity": severity,
        "reason": reason,
        "timestamp": _now(),
    }
    snapshot.setdefault("divergences", []).append(item)
    _divergence_count += 1
    if persist:
        try:
            _append_jsonl(DIVERGENCES_FILE, item)
        except OSError as exc:
            global _last_error
            _last_error = f"divergence_write_error: {exc}"
    return item


def create_lifecycle(payload: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    """Create an isolated shadow lifecycle without touching operational state."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    if not isinstance(persist, bool):
        raise TypeError("persist must be bool")
    _ensure_loaded()
    external = bool(payload.get("external_position") or payload.get("manual_position"))
    lifecycle_id = str(payload.get("lifecycle_id") or "").strip()
    if not lifecycle_id:
        return _result(None, ok=False, status="INVALID_CONTRACT", blocked=True, reasons=["lifecycle_id is required"])
    with _lock:
        existing = _lifecycles.get(lifecycle_id)
        if existing:
            return _result(existing, ok=True, status="LIFECYCLE_ALREADY_EXISTS", duplicate=True)
        reasons: List[str] = []
        warnings: List[str] = []
        if not external:
            if not payload.get("trade_id"):
                reasons.append("trade_id is required for operational lifecycles")
            if not payload.get("signal_id"):
                warnings.append("signal_id is missing")
        if _safe_float(payload.get("quantity_planned"), 0.0) < 0:
            reasons.append("quantity_planned cannot be negative")
        if reasons:
            return _result(None, ok=False, status="INVALID_CONTRACT", blocked=True, reasons=reasons, warnings=warnings)
        state = LifecycleState.MANUAL_POSITION_DETECTED.value if external else LifecycleState.SIGNAL_DETECTED.value
        snapshot = _new_snapshot(payload, state)
        snapshot["warnings"].extend(warnings)
        snapshot["revision"] = 1
        snapshot["history"].append({
            "event_type": LifecycleEvent.EXTERNAL_POSITION_DETECTED.value if external else LifecycleEvent.SIGNAL_CREATED.value,
            "previous_state": "",
            "current_state": state,
            "occurred_at": str(payload.get("occurred_at") or snapshot["created_at"]),
            "received_at": snapshot["created_at"],
            "source_component": str(payload.get("source_component") or "SHADOW_CREATE"),
            "evidence": _json_safe(payload.get("evidence") or {}),
            "applied": True,
        })
        _lifecycles[lifecycle_id] = snapshot
        storage_error = _persist_all() if persist else None
        if storage_error:
            warnings.append(storage_error)
        return _result(snapshot, ok=True, status="LIFECYCLE_CREATED", current_state=state, event_applied=True, warnings=warnings)


def validate_transition(current_state: str, event_type: str) -> Dict[str, Any]:
    """Return the declarative transition decision without applying it."""
    if not isinstance(current_state, str) or not isinstance(event_type, str):
        raise TypeError("current_state and event_type must be strings")
    if current_state not in {item.value for item in LifecycleState}:
        return {"ok": False, "allowed": False, "blocked": True, "reason": "UNKNOWN_STATE", "next_state": None}
    if event_type not in {item.value for item in LifecycleEvent}:
        return {"ok": False, "allowed": False, "blocked": True, "reason": "UNKNOWN_EVENT", "next_state": None}
    target = TRANSITION_MATRIX.get(current_state, {}).get(event_type)
    return {
        "ok": target is not None,
        "allowed": target is not None,
        "blocked": target is None,
        "reason": "ALLOWED" if target is not None else "TRANSITION_NOT_ALLOWED",
        "current_state": current_state,
        "event_type": event_type,
        "next_state": None if target == DYNAMIC else target,
        "dynamic": target == DYNAMIC,
        "shadow_mode": True,
    }


def _event_identity(event: Dict[str, Any], lifecycle_id: str) -> Tuple[str, Dict[str, Any], List[str]]:
    normalized = _json_safe(event)
    occurred_at_supplied = normalized.get("occurred_at") not in (None, "")
    event_type = str(normalized.get("event_type") or "").upper().strip()
    normalized["event_type"] = event_type
    normalized["lifecycle_id"] = str(normalized.get("lifecycle_id") or lifecycle_id)
    normalized["source_component"] = str(normalized.get("source_component") or "UNKNOWN")
    normalized["occurred_at"] = str(normalized.get("occurred_at") or _now())
    normalized["received_at"] = _now()
    normalized["evidence"] = normalized.get("evidence") if isinstance(normalized.get("evidence"), dict) else {}
    normalized["payload"] = normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {}
    warnings: List[str] = []
    event_id = normalized.get("event_id")
    if event_id:
        normalized["event_id"] = str(event_id)
        key_material = f"{lifecycle_id}|{event_type}|{event_id}"
    else:
        stable = dict(normalized)
        stable.pop("received_at", None)
        stable.pop("shadow_event_id", None)
        if not occurred_at_supplied:
            stable.pop("occurred_at", None)
        encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        normalized["shadow_event_id"] = f"CENTRAL-SHADOW-{digest[:24].upper()}"
        key_material = f"{lifecycle_id}|{event_type}|{digest}"
        warnings.append("event_id missing; local shadow_event_id and deterministic content hash used")
    key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    return key, normalized, warnings


def _event_value(event: Dict[str, Any], *keys: str) -> Any:
    for container_name in ("evidence", "payload"):
        container = event.get(container_name)
        if isinstance(container, dict):
            for key in keys:
                if container.get(key) is not None:
                    return container.get(key)
    for key in keys:
        if event.get(key) is not None:
            return event.get(key)
    return None


def _resolve_dynamic_target(snapshot: Dict[str, Any], event: Dict[str, Any], event_type: str) -> str:
    if event_type == LifecycleEvent.ENTRY_FILL_RECORDED.value:
        quantity = max(0.0, _safe_float(_event_value(event, "quantity", "filled_quantity")))
        projected = snapshot["quantity_filled"] + quantity
        planned = snapshot["quantity_planned"]
        explicit_complete = bool(_event_value(event, "complete", "fully_filled"))
        return LifecycleState.ENTRY_CONFIRMED.value if explicit_complete or (planned > 0 and projected + QUANTITY_TOLERANCE >= planned) else LifecycleState.ENTRY_PARTIALLY_FILLED.value
    if event_type == LifecycleEvent.CLOSE_FILL_RECORDED.value:
        quantity = max(0.0, _safe_float(_event_value(event, "quantity", "closed_quantity")))
        projected_closed = snapshot["quantity_closed"] + quantity
        return LifecycleState.CLOSE_CONFIRMED.value if snapshot["quantity_filled"] - projected_closed <= QUANTITY_TOLERANCE else LifecycleState.CLOSE_PARTIALLY_CONFIRMED.value
    target = str(_event_value(event, "target_state", "reconciled_state", "recovered_state") or "")
    allowed_targets = {
        LifecycleState.ENTRY_REJECTED_CONFIRMED.value,
        LifecycleState.ENTRY_PARTIALLY_FILLED.value,
        LifecycleState.ENTRY_CONFIRMED.value,
        LifecycleState.ENTRY_CONFIRMED_STOP_MISSING.value,
        LifecycleState.ENTRY_PROTECTED.value,
        LifecycleState.POSITION_MANAGED.value,
        LifecycleState.RUNNER_PROTECTED.value,
        LifecycleState.CLOSE_PARTIALLY_CONFIRMED.value,
        LifecycleState.CLOSE_CONFIRMED.value,
    }
    return target if target in allowed_targets else ""


def _validate_event_evidence(snapshot: Dict[str, Any], event: Dict[str, Any], event_type: str, target: str) -> List[str]:
    reasons: List[str] = []
    if event.get("lifecycle_id") != snapshot.get("lifecycle_id"):
        reasons.append("event lifecycle_id does not match")
    supplied_trade = _event_value(event, "trade_id")
    if supplied_trade and str(supplied_trade) != str(snapshot.get("trade_id")):
        reasons.append("event trade_id does not match")
    if event_type == LifecycleEvent.ENTRY_INTENT_CREATED.value and not _event_value(event, "client_order_id"):
        reasons.append("client_order_id is required for entry intent")
    if event_type == LifecycleEvent.ENTRY_SUBMITTED.value and not (snapshot.get("client_order_id") or _event_value(event, "client_order_id")):
        reasons.append("client_order_id is required for submission")
    fill_events = {
        LifecycleEvent.ENTRY_FILL_RECORDED.value,
        LifecycleEvent.ENTRY_PARTIAL_RECORDED.value,
        LifecycleEvent.ENTRY_CONFIRMED.value,
        LifecycleEvent.TP50_FILL_RECORDED.value,
        LifecycleEvent.CLOSE_FILL_RECORDED.value,
        LifecycleEvent.CLOSE_PARTIAL_RECORDED.value,
    }
    if event_type in fill_events:
        if not _event_value(event, "fill_id"):
            if event_type == LifecycleEvent.ENTRY_CONFIRMED.value and snapshot.get("quantity_filled", 0.0) > QUANTITY_TOLERANCE:
                pass
            else:
                reasons.append("fill_id is required")
        if _safe_float(_event_value(event, "quantity", "filled_quantity", "closed_quantity")) <= 0:
            if event_type == LifecycleEvent.ENTRY_CONFIRMED.value and snapshot.get("quantity_filled", 0.0) > QUANTITY_TOLERANCE:
                pass
            else:
                reasons.append("positive fill quantity is required")
    quantity = _safe_float(_event_value(event, "quantity", "filled_quantity", "closed_quantity"))
    quantity_open = _safe_float(snapshot.get("quantity_open"))
    if event_type in {LifecycleEvent.CLOSE_FILL_RECORDED.value, LifecycleEvent.TP50_FILL_RECORDED.value}:
        if quantity > quantity_open + QUANTITY_TOLERANCE:
            reasons.append("fill quantity cannot exceed lifecycle open quantity")
    if event_type == LifecycleEvent.TP50_FILL_RECORDED.value:
        requested = snapshot.get("tp50", {}).get("requested_quantity")
        if requested is not None:
            confirmed = _safe_float(snapshot.get("tp50", {}).get("quantity_confirmed"))
            remaining = max(0.0, _safe_float(requested) - confirmed)
            if quantity > remaining + QUANTITY_TOLERANCE:
                reasons.append("TP50 fill quantity cannot exceed remaining requested quantity")
    if event_type == LifecycleEvent.ENTRY_PARTIAL_RECORDED.value:
        planned = _safe_float(snapshot.get("quantity_planned"))
        projected = _safe_float(snapshot.get("quantity_filled")) + quantity
        if planned <= 0:
            reasons.append("quantity_planned must be positive for a partial entry fill")
        elif projected + QUANTITY_TOLERANCE >= planned:
            reasons.append("partial entry fill cannot complete planned quantity")
    if event_type == LifecycleEvent.CLOSE_PARTIAL_RECORDED.value:
        if quantity + QUANTITY_TOLERANCE >= quantity_open:
            reasons.append("partial close fill must remain below lifecycle open quantity")
    if event_type == LifecycleEvent.DISASTER_STOP_CONFIRMED.value or (
        event_type == LifecycleEvent.RECOVERY_COMPLETED.value and target == LifecycleState.ENTRY_PROTECTED.value
    ):
        required = ("order_id", "status", "side", "trigger_price", "protected_quantity", "timestamp")
        missing = [key for key in required if _event_value(event, key) in (None, "")]
        if missing:
            reasons.append("disaster stop evidence missing: " + ", ".join(missing))
        status = str(_event_value(event, "status") or "").upper()
        if status and status not in {"OPEN", "NEW", "ACTIVE"}:
            reasons.append("disaster stop status is not active")
        protected = _safe_float(_event_value(event, "protected_quantity"), -1.0)
        if protected <= 0:
            reasons.append("disaster stop protected_quantity must be positive")
        elif snapshot.get("quantity_open", 0.0) > QUANTITY_TOLERANCE and abs(protected - snapshot["quantity_open"]) > QUANTITY_TOLERANCE:
            reasons.append("disaster stop protected_quantity does not match lifecycle open quantity")
    if event_type == LifecycleEvent.RUNNER_PROTECTION_CONFIRMED.value and _safe_float(_event_value(event, "protected_quantity"), -1.0) < 0:
        reasons.append("runner protected_quantity is required")
    if event_type == LifecycleEvent.CLOSE_CONFIRMED.value and snapshot.get("quantity_open", 0.0) > QUANTITY_TOLERANCE:
        reasons.append("close confirmation requires zero open quantity")
    if event_type == LifecycleEvent.OUTCOME_CONFIRMED.value and not (snapshot.get("outcome_id") or _event_value(event, "outcome_id")):
        reasons.append("outcome_id is required")
    if event_type in {LifecycleEvent.RECONCILIATION_COMPLETED.value, LifecycleEvent.RECOVERY_COMPLETED.value} and not target:
        reasons.append("a factual target_state is required")
    return reasons


def _apply_quantities_and_details(snapshot: Dict[str, Any], event: Dict[str, Any], event_type: str, target: str) -> List[str]:
    warnings: List[str] = []
    client_id = _event_value(event, "client_order_id")
    exchange_id = _event_value(event, "exchange_order_id", "broker_order_id", "order_id")
    if client_id:
        snapshot["client_order_id"] = str(client_id)
    if exchange_id and event_type != LifecycleEvent.DISASTER_STOP_CONFIRMED.value:
        snapshot["exchange_order_id"] = str(exchange_id)

    if event_type in {LifecycleEvent.ENTRY_FILL_RECORDED.value, LifecycleEvent.ENTRY_PARTIAL_RECORDED.value, LifecycleEvent.ENTRY_CONFIRMED.value}:
        fill_id = str(_event_value(event, "fill_id"))
        quantity = _safe_float(_event_value(event, "quantity", "filled_quantity"))
        if fill_id and fill_id not in snapshot["fill_ids"]:
            snapshot["fill_ids"].append(fill_id)
            snapshot["quantity_filled"] += quantity
            snapshot["entry_price_confirmed"] = _event_value(event, "price", "fill_price") or snapshot.get("entry_price_confirmed")
    elif event_type in {LifecycleEvent.TP50_FILL_RECORDED.value, LifecycleEvent.CLOSE_FILL_RECORDED.value, LifecycleEvent.CLOSE_PARTIAL_RECORDED.value}:
        fill_id = str(_event_value(event, "fill_id"))
        quantity = _safe_float(_event_value(event, "quantity", "closed_quantity"))
        if fill_id not in snapshot["fill_ids"]:
            snapshot["fill_ids"].append(fill_id)
            snapshot["quantity_closed"] += quantity
        bucket = snapshot["tp50"] if event_type == LifecycleEvent.TP50_FILL_RECORDED.value else snapshot["close"]
        bucket.setdefault("fill_ids", [])
        if fill_id not in bucket["fill_ids"]:
            bucket["fill_ids"].append(fill_id)
        bucket["quantity_confirmed"] = _safe_float(bucket.get("quantity_confirmed")) + quantity

    if 0 < snapshot["quantity_closed"] - snapshot["quantity_filled"] <= QUANTITY_TOLERANCE:
        snapshot["quantity_closed"] = snapshot["quantity_filled"]
    snapshot["quantity_open"] = snapshot["quantity_filled"] - snapshot["quantity_closed"]
    if abs(snapshot["quantity_open"]) <= QUANTITY_TOLERANCE:
        snapshot["quantity_open"] = 0.0

    if event_type == LifecycleEvent.DISASTER_STOP_REQUESTED.value:
        snapshot["disaster_stop"].update({"requested": True, "confirmed": False, "requested_at": event["received_at"]})
    elif event_type == LifecycleEvent.DISASTER_STOP_CONFIRMED.value:
        snapshot["disaster_stop"] = {
            "confirmed": True,
            "order_id": _event_value(event, "order_id"),
            "status": _event_value(event, "status"),
            "side": _normalize_side(_event_value(event, "side")),
            "trigger_price": _safe_float(_event_value(event, "trigger_price")),
            "protected_quantity": _safe_float(_event_value(event, "protected_quantity")),
            "timestamp": _event_value(event, "timestamp"),
        }
    elif event_type == LifecycleEvent.DISASTER_STOP_FAILED.value:
        snapshot["disaster_stop"].update({"confirmed": False, "failed": True, "reason": _event_value(event, "reason")})
    elif event_type == LifecycleEvent.TP50_REQUESTED.value:
        snapshot["tp50"].update({"requested": True, "requested_quantity": _safe_float(_event_value(event, "quantity")), "confirmed": False})
    elif event_type == LifecycleEvent.TP50_CONFIRMED.value:
        snapshot["tp50"].update({"confirmed": True, "confirmed_at": event["received_at"]})
    elif event_type == LifecycleEvent.RUNNER_PROTECTION_CONFIRMED.value:
        snapshot["runner"] = {"protected": True, "quantity": snapshot["quantity_open"], "evidence": _deepcopy(event["evidence"])}
    elif event_type == LifecycleEvent.BREAK_EVEN_REQUESTED.value:
        snapshot["break_even"] = {"requested": True, "confirmed": False, "evidence": _deepcopy(event["evidence"])}
    elif event_type == LifecycleEvent.BREAK_EVEN_CONFIRMED.value:
        snapshot["break_even"].update({"confirmed": True, "confirmed_at": event["received_at"], "evidence": _deepcopy(event["evidence"])})
    elif event_type == LifecycleEvent.TRAILING_REQUESTED.value:
        snapshot["trailing"] = {"requested": True, "confirmed": False, "evidence": _deepcopy(event["evidence"])}
    elif event_type == LifecycleEvent.TRAILING_CONFIRMED.value:
        snapshot["trailing"].update({"confirmed": True, "confirmed_at": event["received_at"], "evidence": _deepcopy(event["evidence"])})
    elif event_type == LifecycleEvent.CLOSE_REQUESTED.value:
        snapshot["close"].update({"requested": True, "requested_quantity": _safe_float(_event_value(event, "quantity"), snapshot["quantity_open"])})
    elif event_type == LifecycleEvent.CLOSE_CONFIRMED.value or target == LifecycleState.CLOSE_CONFIRMED.value:
        snapshot["close"].update({"confirmed": True, "confirmed_at": event["received_at"]})
    elif event_type in {LifecycleEvent.OUTCOME_CREATED.value, LifecycleEvent.OUTCOME_CONFIRMED.value}:
        outcome = _event_value(event, "outcome")
        if isinstance(outcome, dict):
            snapshot["outcome"].update(_json_safe(outcome))
        outcome_id = _event_value(event, "outcome_id")
        if outcome_id:
            snapshot["outcome_id"] = str(outcome_id)
        snapshot["outcome"]["confirmed"] = event_type == LifecycleEvent.OUTCOME_CONFIRMED.value
    elif event_type == LifecycleEvent.RECONCILIATION_REQUESTED.value:
        snapshot["reconciliation"] = {"required": True, "reason": _event_value(event, "reason"), "evidence": _deepcopy(event["evidence"])}
    elif event_type == LifecycleEvent.RECONCILIATION_COMPLETED.value:
        snapshot["reconciliation"].update({"required": False, "completed": True, "target_state": target, "evidence": _deepcopy(event["evidence"])})
    elif event_type == LifecycleEvent.RECOVERY_REQUESTED.value:
        snapshot["recovery"] = {"required": True, "reason": _event_value(event, "reason"), "evidence": _deepcopy(event["evidence"])}
    elif event_type == LifecycleEvent.RECOVERY_COMPLETED.value:
        snapshot["recovery"].update({"required": False, "completed": True, "target_state": target, "evidence": _deepcopy(event["evidence"])})
        if target == LifecycleState.ENTRY_PROTECTED.value:
            snapshot["disaster_stop"] = {
                "confirmed": True,
                "order_id": _event_value(event, "order_id"),
                "status": _event_value(event, "status"),
                "side": _normalize_side(_event_value(event, "side")),
                "trigger_price": _safe_float(_event_value(event, "trigger_price")),
                "protected_quantity": _safe_float(_event_value(event, "protected_quantity")),
                "timestamp": _event_value(event, "timestamp"),
            }
    elif event_type == LifecycleEvent.EXTERNAL_POSITION_CLASSIFIED.value:
        snapshot["external_position"].update(_deepcopy(event.get("evidence") or {}))

    return warnings


def apply_event(lifecycle_id: str, event: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    """Apply one explicit event to the shadow state machine.

    Invalid lifecycle transitions are reported as passive divergences.  They do
    not mutate lifecycle state and never affect an operational caller.
    """
    global _event_count, _last_error
    if not isinstance(lifecycle_id, str) or not lifecycle_id.strip():
        raise TypeError("lifecycle_id must be a non-empty string")
    if not isinstance(event, dict):
        raise TypeError("event must be a dict")
    if not isinstance(persist, bool):
        raise TypeError("persist must be bool")
    _ensure_loaded()
    with _lock:
        snapshot = _lifecycles.get(lifecycle_id)
        if not snapshot:
            return _result(None, ok=False, status="LIFECYCLE_NOT_FOUND", blocked=True, reasons=["unknown lifecycle_id"])
        key, normalized, warnings = _event_identity(event, lifecycle_id)
        event_type = normalized["event_type"]
        if event_type not in {item.value for item in LifecycleEvent}:
            return _result(snapshot, ok=False, status="UNKNOWN_EVENT", blocked=True, reasons=[event_type or "event_type is required"], warnings=warnings)
        if key in snapshot.get("event_keys", []) or key in snapshot.get("blocked_event_keys", []):
            duplicate_record = {
                "event_type": event_type,
                "event_key": key,
                "received_at": normalized["received_at"],
                "applied": False,
                "duplicate": True,
            }
            snapshot.setdefault("history", []).append(duplicate_record)
            if persist:
                try:
                    _append_jsonl(EVENTS_FILE, {**duplicate_record, "lifecycle_id": lifecycle_id})
                    _atomic_write_snapshot()
                except OSError as exc:
                    _last_error = f"duplicate_persist_error: {exc}"
                    warnings.append(_last_error)
            return _result(snapshot, ok=True, status="DUPLICATE_EVENT", duplicate=True, warnings=warnings)

        fill_event_types = {
            LifecycleEvent.ENTRY_FILL_RECORDED.value,
            LifecycleEvent.ENTRY_PARTIAL_RECORDED.value,
            LifecycleEvent.ENTRY_CONFIRMED.value,
            LifecycleEvent.TP50_FILL_RECORDED.value,
            LifecycleEvent.CLOSE_FILL_RECORDED.value,
            LifecycleEvent.CLOSE_PARTIAL_RECORDED.value,
        }
        supplied_fill_id = _event_value(normalized, "fill_id")
        if event_type in fill_event_types and supplied_fill_id and str(supplied_fill_id) in snapshot.get("fill_ids", []):
            duplicate_record = {
                "event_type": event_type,
                "event_key": key,
                "fill_id": str(supplied_fill_id),
                "received_at": normalized["received_at"],
                "applied": False,
                "duplicate": True,
                "reason": "fill_id already applied",
            }
            snapshot.setdefault("history", []).append(duplicate_record)
            if persist:
                try:
                    _append_jsonl(EVENTS_FILE, {**duplicate_record, "lifecycle_id": lifecycle_id})
                    _atomic_write_snapshot()
                except OSError as exc:
                    _last_error = f"duplicate_fill_persist_error: {exc}"
                    warnings.append(_last_error)
            return _result(snapshot, ok=True, status="DUPLICATE_FILL", duplicate=True, warnings=warnings)

        current = str(snapshot.get("state") or "")
        decision = validate_transition(current, event_type)
        target = TRANSITION_MATRIX.get(current, {}).get(event_type)
        if target == DYNAMIC:
            target = _resolve_dynamic_target(snapshot, normalized, event_type)
        reasons = [] if decision.get("allowed") else ["transition not allowed"]
        if decision.get("allowed"):
            reasons.extend(_validate_event_evidence(snapshot, normalized, event_type, str(target or "")))
        if reasons:
            divergence = _record_divergence(snapshot, "state_transition", current, target or event_type, "WARNING", "; ".join(reasons), persist)
            snapshot.setdefault("blocked_event_keys", []).append(key)
            blocked_record = {
                "event_type": event_type,
                "event_key": key,
                "previous_state": current,
                "current_state": current,
                "received_at": normalized["received_at"],
                "source_component": normalized["source_component"],
                "applied": False,
                "blocked": True,
                "reasons": reasons,
            }
            snapshot.setdefault("history", []).append(blocked_record)
            if persist:
                try:
                    _append_jsonl(EVENTS_FILE, {**blocked_record, "lifecycle_id": lifecycle_id})
                    _atomic_write_snapshot()
                except OSError as exc:
                    _last_error = f"blocked_event_persist_error: {exc}"
                    warnings.append(_last_error)
            return _result(snapshot, ok=False, status="TRANSITION_BLOCKED", previous_state=current, current_state=current, blocked=True, reasons=reasons, warnings=warnings, divergences=[divergence])

        before = _deepcopy(snapshot)
        update_warnings = _apply_quantities_and_details(snapshot, normalized, event_type, str(target))
        warnings.extend(update_warnings)
        snapshot["state"] = str(target)
        snapshot["updated_at"] = normalized["received_at"]
        snapshot["revision"] = int(snapshot.get("revision") or 0) + 1
        snapshot.setdefault("event_keys", []).append(key)
        applied_event = {
            "event_key": key,
            "event_id": normalized.get("event_id"),
            "shadow_event_id": normalized.get("shadow_event_id"),
            "event_type": event_type,
            "lifecycle_id": lifecycle_id,
            "source_component": normalized["source_component"],
            "occurred_at": normalized["occurred_at"],
            "received_at": normalized["received_at"],
            "evidence": _deepcopy(normalized["evidence"]),
            "payload": _deepcopy(normalized["payload"]),
            "previous_state": current,
            "current_state": str(target),
            "quantity_before": before.get("quantity_open"),
            "quantity_after": snapshot.get("quantity_open"),
            "applied": True,
        }
        snapshot.setdefault("events_applied", []).append(applied_event)
        snapshot.setdefault("history", []).append(applied_event)
        snapshot.setdefault("warnings", []).extend(warnings)
        _event_count += 1
        if persist:
            try:
                _append_jsonl(EVENTS_FILE, applied_event)
                _atomic_write_snapshot()
                _last_error = None
            except OSError as exc:
                _last_error = f"event_persist_error: {exc}"
                warnings.append(_last_error)
        return _result(snapshot, ok=True, status="EVENT_APPLIED", previous_state=current, current_state=str(target), event_applied=True, warnings=warnings)


def get_lifecycle(lifecycle_id: str) -> Dict[str, Any]:
    if not isinstance(lifecycle_id, str):
        raise TypeError("lifecycle_id must be a string")
    _ensure_loaded()
    with _lock:
        snapshot = _lifecycles.get(lifecycle_id)
        return {"ok": snapshot is not None, "shadow_mode": True, "lifecycle_id": lifecycle_id, "snapshot": _deepcopy(snapshot or {}), "status": "FOUND" if snapshot else "NOT_FOUND"}


def get_trade_lifecycles(trade_id: str) -> Dict[str, Any]:
    if not isinstance(trade_id, str):
        raise TypeError("trade_id must be a string")
    _ensure_loaded()
    with _lock:
        items = [_deepcopy(item) for item in _lifecycles.values() if item.get("trade_id") == trade_id]
    return {"ok": True, "shadow_mode": True, "trade_id": trade_id, "count": len(items), "lifecycles": items}


def get_open_lifecycles(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if filters is not None and not isinstance(filters, dict):
        raise TypeError("filters must be a dict or None")
    _ensure_loaded()
    terminal = {
        LifecycleState.DECISION_DENIED.value,
        LifecycleState.RISK_DENIED.value,
        LifecycleState.ENTRY_REJECTED_CONFIRMED.value,
        LifecycleState.CLOSE_CONFIRMED.value,
        LifecycleState.OUTCOME_PENDING.value,
        LifecycleState.OUTCOME_RECORDED.value,
        LifecycleState.LEARNING_ELIGIBLE.value,
        LifecycleState.EXTERNAL_EXPOSURE_ONLY.value,
    }
    with _lock:
        items = []
        for item in _lifecycles.values():
            if item.get("state") in terminal:
                continue
            if filters and any(item.get(key) != value for key, value in filters.items()):
                continue
            items.append(_deepcopy(item))
    return {"ok": True, "shadow_mode": True, "count": len(items), "lifecycles": items}


def _local_shadow_event(event_type: str, lifecycle_id: str, reason: str, evidence: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "lifecycle_id": lifecycle_id,
        "source_component": "TRADE_LIFECYCLE_MANAGER_V3_SHADOW",
        "occurred_at": _now(),
        "evidence": {"reason": reason, **_json_safe(evidence or {})},
        "payload": {"reason": reason},
    }


def mark_reconciliation_required(lifecycle_id: str, reason: str, evidence: Optional[Dict[str, Any]] = None, persist: bool = True) -> Dict[str, Any]:
    if not isinstance(reason, str) or not reason.strip():
        raise TypeError("reason must be a non-empty string")
    event = _local_shadow_event(LifecycleEvent.RECONCILIATION_REQUESTED.value, lifecycle_id, reason, evidence)
    return apply_event(lifecycle_id, event, persist=persist)


def mark_recovery_required(lifecycle_id: str, reason: str, evidence: Optional[Dict[str, Any]] = None, persist: bool = True) -> Dict[str, Any]:
    if not isinstance(reason, str) or not reason.strip():
        raise TypeError("reason must be a non-empty string")
    event = _local_shadow_event(LifecycleEvent.RECOVERY_REQUESTED.value, lifecycle_id, reason, evidence)
    return apply_event(lifecycle_id, event, persist=persist)


def record_outcome(lifecycle_id: str, outcome: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    if not isinstance(outcome, dict):
        raise TypeError("outcome must be a dict")
    outcome_id = outcome.get("outcome_id")
    if not outcome_id:
        snapshot = get_lifecycle(lifecycle_id).get("snapshot") or {}
        return _result(snapshot, ok=False, status="OUTCOME_BLOCKED", blocked=True, reasons=["outcome_id is required"])
    current = get_lifecycle(lifecycle_id).get("snapshot") or {}
    if current.get("state") == LifecycleState.CLOSE_CONFIRMED.value:
        requested = apply_event(lifecycle_id, {
            "event_type": LifecycleEvent.OUTCOME_REQUESTED.value,
            "event_id": f"CENTRAL-OUTCOME-REQUEST-{outcome_id}",
            "source_component": "TRADE_LIFECYCLE_MANAGER_V3_SHADOW",
            "evidence": {"outcome_id": outcome_id},
        }, persist=persist)
        if not requested.get("ok"):
            return requested
    created = apply_event(lifecycle_id, {
        "event_type": LifecycleEvent.OUTCOME_CREATED.value,
        "event_id": f"CENTRAL-OUTCOME-CREATED-{outcome_id}",
        "source_component": "TRADE_LIFECYCLE_MANAGER_V3_SHADOW",
        "evidence": {"outcome_id": outcome_id, "outcome": outcome},
    }, persist=persist)
    if not created.get("ok"):
        return created
    return apply_event(lifecycle_id, {
        "event_type": LifecycleEvent.OUTCOME_CONFIRMED.value,
        "event_id": f"CENTRAL-OUTCOME-CONFIRMED-{outcome_id}",
        "source_component": "TRADE_LIFECYCLE_MANAGER_V3_SHADOW",
        "evidence": {"outcome_id": outcome_id, "outcome": outcome},
    }, persist=persist)


def get_lifecycle_history(lifecycle_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        raise TypeError("limit must be a non-negative int or None")
    snapshot = get_lifecycle(lifecycle_id).get("snapshot") or {}
    items = list(snapshot.get("history") or [])
    if limit is not None:
        items = items[-limit:] if limit else []
    return {"ok": bool(snapshot), "shadow_mode": True, "lifecycle_id": lifecycle_id, "count": len(items), "history": _deepcopy(items)}


def _registry_value(record: Dict[str, Any], *keys: str) -> Any:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for key in keys:
        if record.get(key) is not None:
            return record.get(key)
        if metadata.get(key) is not None:
            return metadata.get(key)
    return None


def _has_comparison_evidence(value: Any) -> bool:
    """Return whether a registry value carries useful comparison evidence."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _normalize_optional_text(value: Any, *, upper: bool = False) -> Optional[str]:
    if not _has_comparison_evidence(value):
        return None
    text = str(value).strip()
    return text.upper() if upper else text


def _normalize_optional_symbol(value: Any) -> Optional[str]:
    text = _normalize_optional_text(value, upper=True)
    if text is None:
        return None
    return text.replace("/", "").replace(":USDT", "").replace("-", "")


def _normalize_optional_side(value: Any) -> Optional[str]:
    if not _has_comparison_evidence(value):
        return None
    return _normalize_side(value)


def _normalize_optional_mode(value: Any) -> Optional[str]:
    if not _has_comparison_evidence(value):
        return None
    return _normalize_mode(value)


def _normalize_optional_bool(value: Any) -> Optional[bool]:
    if not _has_comparison_evidence(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "sim", "on", "open", "active", "confirmed"}:
        return True
    if text in {"0", "false", "no", "nao", "não", "off", "closed", "missing", "unconfirmed"}:
        return False
    return None


def _registry_protection_value(record: Dict[str, Any]) -> Optional[bool]:
    explicit = _registry_value(record, "protected", "disaster_stop_confirmed")
    if _has_comparison_evidence(explicit):
        return _normalize_optional_bool(explicit)
    disaster_stop = _registry_value(record, "disaster_stop")
    if isinstance(disaster_stop, dict) and "confirmed" in disaster_stop:
        return _normalize_optional_bool(disaster_stop.get("confirmed"))
    return None


def compare_with_registry(lifecycle_id: str, registry_trade: Dict[str, Any]) -> Dict[str, Any]:
    """Compare with a caller-supplied registry record; never import or mutate it."""
    if not isinstance(registry_trade, dict):
        raise TypeError("registry_trade must be a dict")
    _ensure_loaded()
    with _lock:
        snapshot = _lifecycles.get(lifecycle_id)
        if not snapshot:
            return {"ok": False, "status": "INSUFFICIENT_EVIDENCE", "shadow_mode": True, "differences": [], "reasons": ["lifecycle not found"]}
        registry_exchange_order_id = _registry_value(registry_trade, "exchange_order_id", "broker_order_id", "order_id")
        comparisons = {
            "trade_id": (snapshot.get("trade_id"), _normalize_optional_text(_registry_value(registry_trade, "trade_id"))),
            "bot": (_normalize_optional_text(snapshot.get("bot"), upper=True), _normalize_optional_text(_registry_value(registry_trade, "bot"), upper=True)),
            "setup": (_normalize_optional_text(snapshot.get("setup"), upper=True), _normalize_optional_text(_registry_value(registry_trade, "setup"), upper=True)),
            "symbol": (_normalize_optional_symbol(snapshot.get("symbol")), _normalize_optional_symbol(_registry_value(registry_trade, "symbol"))),
            "side": (_normalize_optional_side(snapshot.get("side")), _normalize_optional_side(_registry_value(registry_trade, "side"))),
            "mode": (_normalize_optional_mode(snapshot.get("mode")), _normalize_optional_mode(_registry_value(registry_trade, "mode", "execution_mode", "registry_mode"))),
            "state": (snapshot.get("state"), _normalize_optional_text(_registry_value(registry_trade, "state", "lifecycle_state"), upper=True)),
            "quantity_open": (snapshot.get("quantity_open"), _registry_value(registry_trade, "quantity_open", "open_qty", "qty")),
            "quantity_closed": (snapshot.get("quantity_closed"), _registry_value(registry_trade, "quantity_closed", "closed_qty")),
            "exchange_order_id": (snapshot.get("exchange_order_id"), _normalize_optional_text(registry_exchange_order_id)),
            "protection": (bool(snapshot.get("disaster_stop", {}).get("confirmed")), _registry_protection_value(registry_trade)),
            "open_closed_status": ("CLOSED" if snapshot.get("state") in {LifecycleState.CLOSE_CONFIRMED.value, LifecycleState.OUTCOME_PENDING.value, LifecycleState.OUTCOME_RECORDED.value, LifecycleState.LEARNING_ELIGIBLE.value} else "OPEN", _normalize_optional_text(_registry_value(registry_trade, "status"), upper=True)),
            "outcome": (snapshot.get("outcome"), _registry_value(registry_trade, "outcome")),
        }
        critical_fields = {"trade_id", "bot", "symbol", "side"}
        differences: List[Dict[str, Any]] = []
        comparable = 0
        matches = 0
        critical_differences = 0
        noncritical_matches = 0
        noncritical_differences = 0
        for field, (shadow_value, registry_value) in comparisons.items():
            if not _has_comparison_evidence(registry_value):
                continue
            if field == "exchange_order_id":
                if not _has_comparison_evidence(shadow_value):
                    continue
                is_critical = True
            else:
                is_critical = field in critical_fields
            comparable += 1
            if shadow_value == registry_value or (field.startswith("quantity_") and abs(_safe_float(shadow_value) - _safe_float(registry_value)) <= QUANTITY_TOLERANCE):
                matches += 1
                if not is_critical:
                    noncritical_matches += 1
                continue
            if is_critical:
                critical_differences += 1
            else:
                noncritical_differences += 1
            severity = "CRITICAL" if is_critical or field in {"quantity_open", "protection", "outcome"} else "WARNING"
            differences.append(_record_divergence(snapshot, field, shadow_value, registry_value, severity, "shadow and current registry differ", persist=True))
        if comparable == 0:
            status = "INSUFFICIENT_EVIDENCE"
        elif critical_differences:
            status = "DIVERGENCE"
        elif not differences:
            status = "MATCH"
        elif noncritical_matches and noncritical_differences:
            status = "PARTIAL_MATCH"
        else:
            status = "DIVERGENCE"
        _persist_all()
        return {
            "ok": status == "MATCH",
            "status": status,
            "shadow_mode": True,
            "lifecycle_id": lifecycle_id,
            "trade_id": snapshot.get("trade_id"),
            "compared_fields": comparable,
            "matching_fields": matches,
            "critical_differences": critical_differences,
            "differences": _deepcopy(differences),
            "snapshot": _deepcopy(snapshot),
        }


def read_shadow_divergences(limit: int = 100) -> Dict[str, Any]:
    if not isinstance(limit, int) or limit < 0:
        raise TypeError("limit must be a non-negative int")
    _ensure_loaded()
    with _lock:
        items = [item for snap in _lifecycles.values() for item in snap.get("divergences", [])]
    return {"ok": True, "shadow_mode": True, "count": len(items[-limit:] if limit else []), "divergences": _deepcopy(items[-limit:] if limit else [])}


def trade_lifecycle_health() -> Dict[str, Any]:
    _ensure_loaded()
    open_result = get_open_lifecycles()
    return {
        "ok": _last_error is None,
        "version": VERSION,
        "shadow_mode": True,
        "loaded": _loaded,
        "lifecycle_count": len(_lifecycles),
        "open_lifecycle_count": open_result["count"],
        "event_count": _event_count,
        "divergence_count": _divergence_count,
        "storage_paths": {
            "snapshot": str(SNAPSHOT_FILE),
            "events": str(EVENTS_FILE),
            "divergences": str(DIVERGENCES_FILE),
        },
        "last_error": _last_error,
        "schema_version": SCHEMA_VERSION,
        "notes": [
            "Shadow Mode only; not an operational authority.",
            "Does not block real execution or alter the current Trade Registry.",
            "Does not call Broker, exchange, network, Redis, Telegram, bots, or runtime.",
        ],
    }


def reset_shadow_storage(confirm: bool = False) -> Dict[str, Any]:
    global _lifecycles, _event_count, _divergence_count, _loaded, _last_error
    if not isinstance(confirm, bool):
        raise TypeError("confirm must be bool")
    if not confirm:
        return {"ok": False, "status": "CONFIRM_REQUIRED", "shadow_mode": True, "reset": False}
    with _lock:
        _lifecycles = {}
        _event_count = 0
        _divergence_count = 0
        _loaded = True
        _last_error = None
        errors = []
        for path in (SNAPSHOT_FILE, EVENTS_FILE, DIVERGENCES_FILE):
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        return {"ok": not errors, "status": "RESET" if not errors else "RESET_PARTIAL", "shadow_mode": True, "reset": True, "errors": errors}


__all__ = [
    "TRADE_LIFECYCLE_SHADOW_MODE",
    "VERSION",
    "SCHEMA_VERSION",
    "LifecycleState",
    "LifecycleEvent",
    "TRANSITION_MATRIX",
    "create_lifecycle",
    "apply_event",
    "get_lifecycle",
    "get_trade_lifecycles",
    "get_open_lifecycles",
    "validate_transition",
    "compare_with_registry",
    "mark_reconciliation_required",
    "mark_recovery_required",
    "record_outcome",
    "get_lifecycle_history",
    "read_shadow_divergences",
    "trade_lifecycle_health",
    "reset_shadow_storage",
]
