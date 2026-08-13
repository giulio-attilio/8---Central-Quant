"""Passive runtime adapter for Trade Lifecycle Manager V3 Shadow Mode.

The adapter consumes caller-supplied facts, never acquires operational authority,
and never imports Broker or writes to the operational Trade Registry.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import trade_lifecycle_manager as lifecycle_manager


VERSION = "1.0.0-SHADOW"
MODE = "SHADOW"
SHADOW_STORAGE_LOCK_TIMEOUT_SECONDS = 0.25
_TRUE = {"1", "true", "yes", "sim", "on"}
_FALSE = {"0", "false", "no", "nao", "não", "off", "disabled"}
LOGGER = logging.getLogger(__name__)
_STORAGE_LOCKS_GUARD = threading.RLock()
_STORAGE_LOCKS: Dict[str, threading.RLock] = {}
_VALIDATION_EVENT_IDS: Dict[str, set[str]] = {}
LEGACY_EVENT_MAP = {
    "SIGNAL": "SIGNAL_CREATED",
    "SIGNAL_CREATED": "SIGNAL_CREATED",
    "DECISION_PENDING": "DECISION_PENDING_RECORDED",
    "DECISION_ALLOWED": "DECISION_ALLOWED_RECORDED",
    "DECISION_DENIED": "DECISION_DENIED_RECORDED",
    "RISK_PENDING": "RISK_PENDING_RECORDED",
    "RISK_APPROVED": "RISK_APPROVED_RECORDED",
    "RISK_DENIED": "RISK_DENIED_RECORDED",
    "ENTRY_INTENT": "ENTRY_INTENT_CREATED",
    "ENTRY_SUBMITTED": "ENTRY_SUBMITTED",
    "ENTRY_UNKNOWN": "ENTRY_SUBMISSION_BECAME_UNKNOWN",
    "ENTRY_FILL": "ENTRY_FILL_RECORDED",
    "ENTRY_CONFIRMED": "ENTRY_CONFIRMED",
    "STOP_REQUESTED": "DISASTER_STOP_REQUESTED",
    "STOP_CONFIRMED": "DISASTER_STOP_CONFIRMED",
    "STOP_FAILED": "DISASTER_STOP_FAILED",
    "POSITION_MANAGED": "POSITION_MANAGEMENT_STARTED",
    "TRADE_UPDATED": "TRADE_UPDATED",
    "TP50_REQUESTED": "TP50_REQUESTED",
    "TP50_FILL": "TP50_FILL_RECORDED",
    "TP50_CONFIRMED": "TP50_CONFIRMED",
    "RUNNER_PROTECTED": "RUNNER_PROTECTION_CONFIRMED",
    "BREAK_EVEN_REQUESTED": "BREAK_EVEN_REQUESTED",
    "BREAK_EVEN_CONFIRMED": "BREAK_EVEN_CONFIRMED",
    "TRAILING_REQUESTED": "TRAILING_REQUESTED",
    "TRAILING_CONFIRMED": "TRAILING_CONFIRMED",
    "CLOSE_REQUESTED": "CLOSE_REQUESTED",
    "CLOSE_FILL": "CLOSE_FILL_RECORDED",
    "CLOSE_CONFIRMED": "CLOSE_CONFIRMED",
    "OUTCOME": "OUTCOME_CONFIRMED",
    "EXTERNAL_POSITION": "EXTERNAL_POSITION_DETECTED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_epoch(value: Any) -> Optional[float]:
    """Parse persisted factual timestamps for conservative ordering checks."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        pass
    for pattern in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _first(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    for key in keys:
        if record.get(key) not in (None, ""):
            return record.get(key)
        if metadata.get(key) not in (None, ""):
            return metadata.get(key)
    return None


def _canonical_identity(record: Mapping[str, Any]) -> Dict[str, str]:
    identity = {
        "trade_id": _first(record, ("trade_id", "canonical_trade_id")),
        "registry_id": _first(record, ("registry_id",)),
        "execution_id": _first(record, ("execution_id",)),
        "decision_id": _first(record, ("decision_id",)),
        "signal_id": _first(record, ("signal_id",)),
    }
    value = next((str(value).strip() for value in identity.values() if value not in (None, "")), "")
    if not value:
        stable = {
            "bot": _first(record, ("bot",)),
            "setup": _first(record, ("setup",)),
            "source_id": _first(record, ("source_id", "id")),
            "opened_at": _first(record, ("opened_at", "created_at")),
        }
        if not any(stable.values()):
            return {"value": "", "source": "INSUFFICIENT_IDENTITY"}
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return {"value": f"CENTRAL-SHADOW-{digest.upper()}", "source": "DETERMINISTIC_FALLBACK"}
    source = next(key for key, item in identity.items() if item not in (None, ""))
    return {"value": value, "source": source.upper()}


def _resolve_lifecycle_id(record: Mapping[str, Any], canonical_identity: Mapping[str, str], *, external: bool = False) -> Dict[str, str]:
    explicit = _first(record, ("lifecycle_id",))
    if explicit is not None and str(explicit).strip():
        return {"value": str(explicit), "source": "EXPLICIT_LIFECYCLE_ID"}
    if external:
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return {"value": f"CENTRAL-SHADOW-EXTERNAL-{digest.upper()}", "source": "EXTERNAL_POSITION"}
    identity_value = str(canonical_identity.get("value") or "").strip()
    if not identity_value:
        return {"value": "", "source": "INSUFFICIENT_IDENTITY"}
    material = {
        "schema": "CENTRAL_SHADOW_LIFECYCLE_ID_V1",
        "identity_source": str(canonical_identity.get("source") or ""),
        "identity_value": identity_value,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return {"value": f"CENTRAL-SHADOW-LIFECYCLE-{digest.upper()}", "source": "DERIVED_CANONICAL_IDENTITY"}


def _upper_first(record: Mapping[str, Any], keys: Iterable[str]) -> str:
    return str(_first(record, keys) or "").upper().strip()


def _normalized_symbol(value: Any) -> str:
    text = str(value or "").upper().strip().replace("-", "").replace("/", "")
    return text.split(":", 1)[0]


def _normalized_side(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"BUY", "LONG"}:
        return "LONG"
    if text in {"SELL", "SHORT"}:
        return "SHORT"
    return text


def _normalized_mode(value: Any) -> str:
    text = str(value or "").upper().strip()
    aliases = {"REAL": "LIVE", "DRY_RUN": "VERIFY", "OBSERVATION_ONLY": "VERIFY"}
    return aliases.get(text, text)


def _numbers_match(left: Any, right: Any) -> bool:
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(1e-9, max(abs(a), abs(b)) * 1e-9)


def _positive_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _nested_mapping(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _first(record, (key,))
    return value if isinstance(value, Mapping) else {}


def _explicit_live_registry_allow(record: Mapping[str, Any], *, statuses: set[str]) -> bool:
    """Accept only an authoritative, non-external Registry LIVE fact."""
    if _upper_first(record, ("source_component",)) != "TRADE_REGISTRY":
        return False
    if _normalized_mode(_upper_first(record, ("mode", "execution_mode", "registry_mode"))) != "LIVE":
        return False
    if _upper_first(record, ("status",)) not in statuses:
        return False
    if bool(_first(record, ("external_position", "manual_position"))):
        return False
    required = ("trade_id", "bot", "setup", "symbol", "side")
    if any(_first(record, (field,)) in (None, "") for field in required):
        return False
    decision = _first(record, ("execution_decision",))
    if not isinstance(decision, Mapping):
        return False
    return bool(
        decision.get("allowed") is True
        and str(decision.get("decision") or "").upper().strip() == "ALLOW"
    )


def _registry_quantity(record: Mapping[str, Any]) -> Optional[float]:
    return _positive_float(_first(record, (
        "initial_quantity", "initial_qty", "original_quantity", "quantity", "qty",
    )))


def _registry_open_quantity(record: Mapping[str, Any]) -> Any:
    """Project CLOSED as zero even when Registry retains historical remaining_qty."""
    if _upper_first(record, ("status",)) == "CLOSED":
        return 0.0
    remaining = _first(record, ("remaining_quantity", "remaining_qty", "quantity_open", "open_qty"))
    return remaining if remaining not in (None, "") else _first(record, ("quantity", "qty"))


def _registry_entry_evidence(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Build position-open evidence without fabricating a broker fill identifier."""
    if not _explicit_live_registry_allow(record, statuses={"OPEN"}):
        return None
    submission = _live_submission_evidence(record)
    quantity = _registry_quantity(record)
    confirmed_price = _first(record, (
        "entry_price_confirmed", "executed_price", "average_price", "fill_price", "average",
    ))
    reference_price = _first(record, ("broker_entry_reference",))
    theoretical_price = _first(record, ("entry_price_theoretical", "entry_price", "entry"))
    if submission is None or quantity is None:
        return None
    evidence = {
        **submission,
        "registry_live_open_post_ack": True,
        "registry_status": "OPEN",
        "execution_sent": True,
        "quantity": quantity,
        "filled_quantity": quantity,
        "opened_at": _first(record, ("opened_at",)),
        "timestamp": _first(record, ("entry_confirmed_at", "opened_at", "last_update")),
    }
    if _positive_float(confirmed_price) is not None:
        evidence["entry_price_confirmed"] = float(confirmed_price)
    if _positive_float(reference_price) is not None:
        evidence["entry_price_reference"] = float(reference_price)
    if _positive_float(theoretical_price) is not None:
        evidence["entry_price_theoretical"] = float(theoretical_price)
    return evidence


def _registry_stop_update_failure(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a factual unprotected stop-update failure, if Registry recorded one."""
    update = _nested_mapping(record, "stop_update")
    failed = _first(record, ("stop_update_failed",)) is True or update.get("ok") is False
    if not failed:
        return None
    rollback = update.get("rollback") if isinstance(update.get("rollback"), Mapping) else {}
    final_protection = bool(
        _first(record, ("stop_update_final_protection_confirmed",)) is True
        or (rollback.get("ok") is True and rollback.get("order_id"))
        or _upper_first(record, ("broker_stop_status",)) == "ROLLBACK_PROTECTED"
    )
    if final_protection:
        return None
    reason = _upper_first(record, ("stop_update_reason", "management_reason"))
    aliases = {"BE": "BREAK_EVEN", "BREAKEVEN": "BREAK_EVEN", "BREAK-EVEN": "BREAK_EVEN"}
    return {
        "trade_id": str(_first(record, ("trade_id",)) or ""),
        "reason": aliases.get(reason, reason) or "STOP_UPDATE_FAILED",
        "status": _first(record, ("stop_update_status",)) or update.get("status") or "STOP_UPDATE_FAILED",
        "timestamp": _first(record, ("stop_update_confirmed_at", "last_update", "updated_at")),
        "stop_update_failed": True,
        "registry_source_component": "TRADE_REGISTRY",
        "evidence": _json_safe(update),
    }


def _registry_stop_evidence(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Return complete physical-stop evidence already persisted by Registry."""
    if _registry_stop_update_failure(record) is not None:
        return None
    nested = _nested_mapping(record, "disaster_stop")
    order_id = _first(record, ("broker_stop_order_id", "disaster_stop_order_id")) or nested.get("order_id")
    raw_status = _first(record, ("broker_stop_status", "disaster_stop_status")) or nested.get("status")
    action_side = _first(record, ("broker_stop_side", "disaster_stop_side", "stop_action_side")) or nested.get("side")
    symbol = _first(record, ("broker_stop_symbol", "disaster_stop_symbol")) or nested.get("symbol") or _first(record, ("symbol",))
    trigger_price = _first(record, ("broker_stop_price", "disaster_stop_price")) or nested.get("trigger_price") or nested.get("stop_price")
    quantity = _first(record, ("broker_stop_amount", "disaster_stop_quantity", "protected_quantity")) or nested.get("protected_quantity") or nested.get("amount")
    timestamp = _first(record, ("broker_stop_confirmed_at", "disaster_stop_confirmed_at")) or nested.get("timestamp")
    if any(value in (None, "") for value in (order_id, raw_status, action_side, symbol, trigger_price, quantity, timestamp)):
        return None
    status_text = str(raw_status).upper().strip()
    active_statuses = {
        "OPEN", "NEW", "ACTIVE", "DISASTER_STOP_CREATED", "STOP_REPLACED",
        "STOP_REPLACED_CONFIRMED", "STOP_REPLACED_EDIT", "STOP_REPLACED_CANCEL_CREATE",
        "ROLLBACK_PROTECTED",
    }
    if status_text not in active_statuses:
        return None
    position_side = _normalized_side(_first(record, ("side",)))
    protective_side = _normalized_side(action_side)
    expected_action = "SHORT" if position_side == "LONG" else "LONG" if position_side == "SHORT" else ""
    if not expected_action or protective_side != expected_action:
        return None
    protected = _positive_float(quantity)
    price = _positive_float(trigger_price)
    expected_quantity = _positive_float(_first(record, ("remaining_quantity", "remaining_qty", "quantity_open", "open_qty"))) or _registry_quantity(record)
    if protected is None or price is None or expected_quantity is None or not _numbers_match(protected, expected_quantity):
        return None
    if _normalized_symbol(symbol) != _normalized_symbol(_first(record, ("symbol",))):
        return None
    return {
        "trade_id": str(_first(record, ("trade_id",)) or ""),
        "order_id": str(order_id),
        "status": "ACTIVE",
        "broker_status": status_text,
        "side": "SELL" if protective_side == "SHORT" else "BUY",
        "position_side": position_side,
        "symbol": _normalized_symbol(symbol),
        "trigger_price": price,
        "protected_quantity": protected,
        "timestamp": str(timestamp),
        "registry_source_component": "TRADE_REGISTRY",
        "physical_stop_confirmed": True,
    }


def _registry_initial_stop_failure(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Return explicit initial disaster-stop failure evidence, never an inference."""
    if _first(record, ("disaster_stop_confirmed", "protected")) is not False:
        return None
    status = _upper_first(record, ("broker_stop_status", "disaster_stop_status"))
    if not status or not any(marker in status for marker in ("ERROR", "FAILED", "REJECTED", "MISSING", "UNPROTECTED")):
        return None
    return {
        "trade_id": str(_first(record, ("trade_id",)) or ""),
        "reason": str(_first(record, ("disaster_stop_error", "broker_stop_error")) or status),
        "status": status,
        "timestamp": _first(record, ("broker_stop_confirmed_at", "last_update", "updated_at")),
        "registry_source_component": "TRADE_REGISTRY",
        "physical_stop_confirmed": False,
    }


def _registry_tp50_evidence(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    confirmed = _first(record, ("broker_reduction_confirmed", "tp50_real_executed", "tp50_confirmed")) is True
    status = _upper_first(record, ("tp50_status",))
    confirmed = confirmed or status.startswith("REAL_EXECUTED")
    order_id = _first(record, ("tp50_broker_order_id", "tp50_real_order_id", "tp50_order_id"))
    quantity = _positive_float(_first(record, ("tp50_filled_quantity", "tp50_quantity", "tp50_amount")))
    # Falcon currently projects the factual Registry update time rather than a
    # dedicated TP50 timestamp.  Keep the preferred typed fields, then use that
    # persisted Registry timestamp; never synthesize one here.
    timestamp = _first(record, (
        "tp50_confirmed_at", "tp50_timestamp", "last_update", "updated_at",
    ))
    if not confirmed or order_id in (None, "") or quantity is None or timestamp in (None, ""):
        return None
    return {
        "trade_id": str(_first(record, ("trade_id",)) or ""),
        "broker_reduction_confirmed": True,
        "broker_order_id": str(order_id),
        "order_id": str(order_id),
        "quantity": quantity,
        "closed_quantity": quantity,
        "timestamp": str(timestamp),
        "registry_source_component": "TRADE_REGISTRY",
    }


def _registry_stop_management(record: Mapping[str, Any], expected_reason: str) -> Optional[Dict[str, Any]]:
    reason = _upper_first(record, ("stop_update_reason", "management_reason"))
    aliases = {"BE": "BREAK_EVEN", "BREAKEVEN": "BREAK_EVEN", "BREAK-EVEN": "BREAK_EVEN"}
    reason = aliases.get(reason, reason)
    if reason != expected_reason:
        return None
    update = _nested_mapping(record, "stop_update")
    order_id = _first(record, ("broker_stop_order_id", "disaster_stop_order_id")) or update.get("new_order_id") or update.get("order_id")
    price = _first(record, ("broker_stop_price", "stop_price", "sl")) or update.get("new_stop_price") or update.get("stop_price")
    timestamp = _first(record, (
        "stop_update_confirmed_at", "stop_update_timestamp", "last_update", "updated_at",
    )) or update.get("timestamp")
    confirmed = _first(record, ("stop_update_confirmed",)) is True or update.get("ok") is True
    if not confirmed or order_id in (None, "") or _positive_float(price) is None or timestamp in (None, ""):
        return None
    return {
        "trade_id": str(_first(record, ("trade_id",)) or ""),
        "order_id": str(order_id),
        "stop_price": float(price),
        "timestamp": str(timestamp),
        "reason": expected_reason,
        "broker_stop_update_confirmed": True,
        "registry_source_component": "TRADE_REGISTRY",
    }


def _registry_close_evidence(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if not _explicit_live_registry_allow(record, statuses={"CLOSED"}):
        return None
    closed_at = _first(record, ("closed_at",))
    close_reason = _first(record, ("close_reason", "exit_reason", "reason"))
    total_quantity = _positive_float(_first(record, ("closed_quantity", "quantity_closed"))) or _registry_quantity(record)
    final_quantity = _positive_float(_first(record, (
        "final_close_quantity", "close_quantity", "remaining_quantity", "remaining_qty",
        "quantity_open", "open_qty",
    )))
    if final_quantity is None and total_quantity is not None:
        tp50_quantity = _positive_float(_first(record, ("tp50_filled_quantity", "tp50_quantity", "tp50_amount"))) or 0.0
        final_quantity = max(0.0, total_quantity - tp50_quantity) or total_quantity
    if closed_at in (None, "") or close_reason in (None, "") or final_quantity is None or total_quantity is None:
        return None
    return {
        "trade_id": str(_first(record, ("trade_id",)) or ""),
        "registry_live_closed_factual": True,
        "registry_status": "CLOSED",
        "mode": "LIVE",
        "closed_at": str(closed_at),
        "close_reason": str(close_reason),
        "quantity": final_quantity,
        "final_close_quantity": final_quantity,
        "closed_quantity": total_quantity,
        "exit_price": _first(record, ("exit_price",)),
        "result_pct": _first(record, ("result_pct", "pnl_pct")),
        "result_r": _first(record, ("result_r", "pnl_r")),
        "broker_close_order_id": _first(record, ("broker_close_order_id",)),
        "registry_source_component": "TRADE_REGISTRY",
    }


def _registry_protection(record: Mapping[str, Any]) -> tuple[bool, str]:
    confirmed = _first(record, ("protected", "disaster_stop_confirmed")) is True
    stop_order_id = _first(record, ("broker_stop_order_id", "disaster_stop_order_id"))
    nested = _first(record, ("disaster_stop",))
    if isinstance(nested, Mapping):
        confirmed = confirmed or nested.get("confirmed") is True
        stop_order_id = stop_order_id or nested.get("order_id")
    return confirmed, str(stop_order_id or "").strip()


def _manager_current_stop_fact(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the newest confirmed physical-stop fact without regressing on retries."""
    candidates = []
    disaster_stop = snapshot.get("disaster_stop") if isinstance(snapshot.get("disaster_stop"), Mapping) else {}
    if disaster_stop.get("confirmed") is True and disaster_stop.get("order_id"):
        candidates.append({
            "order_id": str(disaster_stop.get("order_id")),
            "timestamp": disaster_stop.get("timestamp"),
            "priority": 2,
        })
    for bucket_name, confirmation_key in (
        ("trailing", "confirmed"),
        ("break_even", "confirmed"),
        ("runner", "protected"),
    ):
        bucket = snapshot.get(bucket_name) if isinstance(snapshot.get(bucket_name), Mapping) else {}
        if bucket.get(confirmation_key) is not True:
            continue
        evidence = bucket.get("evidence") if isinstance(bucket.get("evidence"), Mapping) else {}
        order_id = evidence.get("order_id") or evidence.get("broker_order_id")
        if order_id:
            candidates.append({
                "order_id": str(order_id),
                "timestamp": evidence.get("timestamp") or bucket.get("confirmed_at"),
                "priority": 1,
            })
    if not candidates:
        return {"confirmed": False, "order_id": "", "timestamp": None}
    newest = max(
        candidates,
        key=lambda item: (
            _timestamp_epoch(item.get("timestamp")) is not None,
            _timestamp_epoch(item.get("timestamp")) or float("-inf"),
            item.get("priority", 0),
        ),
    )
    return {"confirmed": True, **newest}


def _manager_current_stop(snapshot: Mapping[str, Any]) -> tuple[bool, str]:
    fact = _manager_current_stop_fact(snapshot)
    return bool(fact.get("confirmed")), str(fact.get("order_id") or "")


def _should_refresh_manager_stop(snapshot: Mapping[str, Any], factual_stop: Mapping[str, Any]) -> bool:
    """Accept a changed physical stop only when its evidence is factually newer."""
    candidate_id = str(factual_stop.get("order_id") or "")
    if not candidate_id:
        return False
    canonical = snapshot.get("disaster_stop") if isinstance(snapshot.get("disaster_stop"), Mapping) else {}
    if canonical.get("confirmed") is not True:
        return True
    current_id = str(canonical.get("order_id") or "")
    if not current_id:
        return True
    if candidate_id == current_id:
        return False
    candidate_time = _timestamp_epoch(factual_stop.get("timestamp"))
    current_time = _timestamp_epoch(canonical.get("timestamp"))
    if candidate_time is None:
        return False
    return current_time is None or candidate_time > current_time


def _pending_live_decision_steps(state: Any, evidence: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    sequence = (
        ("SIGNAL_DETECTED", "DECISION_PENDING_RECORDED"),
        ("DECISION_PENDING", "DECISION_ALLOWED_RECORDED"),
        ("DECISION_ALLOWED", "RISK_PENDING_RECORDED"),
        ("RISK_PENDING", "RISK_APPROVED_RECORDED"),
    )
    current = str(state or "SIGNAL_DETECTED").upper().strip()
    start = next((index for index, (source, _) in enumerate(sequence) if source == current), len(sequence))
    return [(event_type, evidence) for _, event_type in sequence[start:]]


def _derived_paper_event_id(source_event_id: str, lifecycle_id: str, event_type: str) -> str:
    material = f"{source_event_id}|{lifecycle_id}|{event_type}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32].upper()
    return f"CENTRAL-SHADOW-PAPER-EVENT-{digest}"


def _paper_event(event_type: str, source_event_id: str, lifecycle_id: str, trade_id: str, original: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = {
        "trade_id": trade_id,
        "mode": "PAPER",
        "registry_status": _upper_first(original, ("status",)),
        "registry_source_component": "TRADE_REGISTRY",
        "source_event_id": source_event_id,
    }
    if event_type == "PAPER_POSITION_CLOSED":
        evidence["closed_at"] = _first(original, ("closed_at",))
        for key in ("exit_price", "close_reason", "pnl_pct", "pnl_r", "result_pct", "result_r"):
            value = _first(original, (key,))
            if value not in (None, ""):
                evidence[key] = value
    occurred_at = _first(original, ("occurred_at", "timestamp", "updated_at", "last_update", "closed_at", "opened_at")) or _now()
    return {
        "event_id": _derived_paper_event_id(source_event_id, lifecycle_id, event_type),
        "event_type": event_type,
        "lifecycle_id": lifecycle_id,
        "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
        "occurred_at": str(occurred_at),
        "evidence": evidence,
        "payload": {"registry_event_type": "SIGNAL_CREATED" if event_type == "PAPER_POSITION_OPENED" else "CLOSE_CONFIRMED"},
    }


def _manager_result_summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "event_applied": bool(result.get("event_applied")),
        "duplicate": bool(result.get("duplicate")),
        "lifecycle_id": result.get("lifecycle_id"),
        "trade_id": result.get("trade_id"),
        "current_state": result.get("current_state"),
    }


def _storage_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _STORAGE_LOCKS_GUARD:
        return _STORAGE_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _cross_process_file_lock(path: Path):
    """Serialize validation-journal append across local worker processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + max(0.0, float(SHADOW_STORAGE_LOCK_TIMEOUT_SECONDS))
        if os.name == "nt":
            import msvcrt

            acquired = False
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError as exc:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("shadow validation storage lock timed out") from exc
                    time.sleep(min(0.005, remaining))
            try:
                yield
            finally:
                if acquired:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            acquired = False
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except (BlockingIOError, OSError) as exc:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("shadow validation storage lock timed out") from exc
                    time.sleep(min(0.005, remaining))
            try:
                yield
            finally:
                if acquired:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _explicit_live_allow(record: Mapping[str, Any]) -> bool:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    decision = record.get("execution_decision")
    if not isinstance(decision, Mapping):
        decision = metadata.get("execution_decision")
    mode = _upper_first(record, ("mode", "execution_mode", "registry_mode"))
    return bool(
        _upper_first(record, ("source_component",)) == "TRADE_REGISTRY"
        and mode in {"LIVE", "REAL"}
        and isinstance(decision, Mapping)
        and decision.get("allowed") is True
        and str(decision.get("decision") or "").upper().strip() == "ALLOW"
    )


def _live_submission_evidence(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if _upper_first(record, ("source_component",)) != "TRADE_REGISTRY":
        return None
    if _upper_first(record, ("mode", "execution_mode", "registry_mode")) not in {"LIVE", "REAL"}:
        return None
    if _first(record, ("execution_sent",)) is not True:
        return None
    client_order_id = _first(record, ("client_order_id",))
    # ``order_id`` is intentionally excluded: without a typed field it may be
    # the disaster-stop order rather than the entry order.
    exchange_order_id = _first(record, ("broker_order_id", "exchange_order_id"))
    if client_order_id in (None, "") or exchange_order_id in (None, ""):
        return None
    return {
        "client_order_id": str(client_order_id),
        "exchange_order_id": str(exchange_order_id),
        "trade_id": str(_first(record, ("trade_id", "canonical_trade_id")) or ""),
        "mode": _upper_first(record, ("mode", "execution_mode", "registry_mode")),
        "timestamp": _first(record, (
            "entry_submitted_at", "execution_sent_at", "broker_ack_at",
            "last_update", "updated_at", "opened_at",
        )),
        "registry_source_component": "TRADE_REGISTRY",
    }


def _derived_live_event_id(lifecycle_id: str, event_type: str, evidence: Mapping[str, Any]) -> str:
    material = {
        "schema": "CENTRAL_SHADOW_LIVE_FACT_V1",
        "lifecycle_id": lifecycle_id,
        "event_type": event_type,
        "trade_id": evidence.get("trade_id"),
        "decision_id": evidence.get("decision_id"),
        "client_order_id": evidence.get("client_order_id"),
        "exchange_order_id": evidence.get("exchange_order_id"),
        "broker_order_id": evidence.get("broker_order_id"),
        "order_id": evidence.get("order_id"),
        "stop_price": evidence.get("stop_price"),
        "trigger_price": evidence.get("trigger_price"),
        "quantity": evidence.get("quantity"),
        "closed_quantity": evidence.get("closed_quantity"),
        "reason": evidence.get("reason") or evidence.get("close_reason"),
        "outcome_id": evidence.get("outcome_id"),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32].upper()
    return f"CENTRAL-SHADOW-LIVE-EVENT-{digest}"


def _live_event(lifecycle_id: str, event_type: str, occurred_at: Any, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": _derived_live_event_id(lifecycle_id, event_type, evidence),
        "event_type": event_type,
        "lifecycle_id": lifecycle_id,
        "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
        "occurred_at": str(occurred_at or _now()),
        "evidence": _json_safe(evidence),
        "payload": {"registry_observation": True, "operational_authority": False},
    }


class TradeLifecycleShadowRuntimeAdapter:
    """Thread-safe, fail-open adapter with no operational authority."""

    def __init__(self, *, enabled: Optional[bool] = None, data_dir: Optional[Path] = None, manager: Any = None) -> None:
        raw_enabled = os.getenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED")
        configured = True if raw_enabled is None else raw_enabled.strip().lower() not in _FALSE
        self.enabled = configured if enabled is None else bool(enabled)
        self.manager = manager or lifecycle_manager
        root = Path(data_dir) if data_dir is not None else Path(os.getenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR") or os.getenv("CENTRAL_DATA_DIR") or Path(__file__).resolve().parent / "data")
        self.events_file = root / "trade_lifecycle_shadow_runtime_events.jsonl"
        self.divergences_file = root / "trade_lifecycle_shadow_runtime_divergences.jsonl"
        self.state_file = root / "trade_lifecycle_shadow_runtime_state.json"
        self._lock = threading.RLock()
        self._seen: set[str] = set()
        self._divergence_keys: set[str] = set()
        self._metrics = {"observed": 0, "applied": 0, "duplicate": 0, "blocked": 0, "errors": 0, "reconciled": 0, "divergences": 0}
        self._last_error: Optional[str] = None

    def _result(self, status: str, *, ok: bool = True, **extra: Any) -> Dict[str, Any]:
        return {
            "ok": ok,
            "status": status,
            "mode": MODE,
            "shadow_mode": True,
            "fail_open": True,
            "production_blocked": False,
            "operational_result_preserved": True,
            "operational_authority": False,
            **extra,
        }

    def _append(self, path: Path, item: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

    def _persist_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temp.write_text(json.dumps({"version": VERSION, "updated_at": _now(), "metrics": self._metrics}, indent=2), encoding="utf-8")
        os.replace(temp, self.state_file)

    def _event_id(self, event_type: str, identity: str, source: Mapping[str, Any]) -> str:
        supplied = _first(source, ("event_id",))
        if supplied:
            return str(supplied)
        material = {
            "event_type": event_type,
            "identity": identity,
            "source_event_id": _first(source, ("source_event_id", "registry_event_id", "execution_id", "fill_id", "order_id")),
            "occurred_at": _first(source, ("occurred_at", "timestamp", "updated_at", "last_update", "opened_at", "closed_at")),
            "sequence": _first(source, ("sequence", "revision", "version", "attempt")),
        }
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()
        return f"CENTRAL-SHADOW-EVENT-{digest[:32].upper()}"

    def _shadow_validation_event(
        self,
        original: Mapping[str, Any],
        lifecycle_id: str,
        comparison: Mapping[str, Any],
        manager_snapshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        identity = {
            key: _first(original, (key,))
            for key in (
                "trade_id", "registry_id", "lifecycle_id", "decision_id", "signal_id",
                "client_order_id", "broker_order_id", "exchange_order_id", "order_id",
                "broker_stop_order_id", "disaster_stop_order_id", "outcome_id",
            )
        }
        identity["lifecycle_id"] = identity.get("lifecycle_id") or lifecycle_id
        stable_identity = {
            key: identity.get(key)
            for key in (
                "trade_id", "registry_id", "lifecycle_id", "client_order_id",
                "broker_order_id", "exchange_order_id", "broker_stop_order_id",
                "disaster_stop_order_id", "outcome_id",
            )
        }
        material = {
            "schema": "CENTRAL_SHADOW_VALIDATED_V1",
            "identity": stable_identity,
            "opened_at": _first(original, ("opened_at", "created_at")),
            "closed_at": _first(original, ("closed_at",)),
            "status": _upper_first(original, ("status",)),
            "quantity_open": _registry_open_quantity(original),
            "exit_price": _first(original, ("exit_price",)),
            "result_pct": _first(original, ("result_pct", "pnl_pct")),
            "result_r": _first(original, ("result_r", "pnl_r")),
            "pnl_usdt": _first(original, ("pnl_usdt", "realized_pnl")),
            "outcome_id": manager_snapshot.get("outcome_id"),
        }
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32].upper()
        mode = _upper_first(original, ("mode", "execution_mode", "registry_mode"))
        registry_status = _upper_first(original, ("status",))
        validated_fields = ["trade_id", "bot", "setup", "symbol", "side", "mode", "status"]
        if mode in {"LIVE", "REAL"}:
            validated_fields.extend(["quantity_open", "client_order_id", "exchange_order_id"])
            if registry_status == "OPEN":
                validated_fields.extend(["protection", "disaster_stop_order_id"])
            elif registry_status == "CLOSED":
                validated_fields.extend([
                    "lifecycle_terminal", "close_confirmed", "outcome_recorded",
                    "quantity_closed", "closed_at", "close_reason",
                ])
        protection_confirmed, stop_order_id = _registry_protection(original)
        validated_values = {
            "trade_id": identity.get("trade_id"),
            "bot": _first(original, ("bot",)),
            "setup": _first(original, ("setup",)),
            "symbol": _first(original, ("symbol",)),
            "side": _first(original, ("side",)),
            "mode": mode,
            "status": registry_status,
            "quantity_open": _registry_open_quantity(original),
            "client_order_id": identity.get("client_order_id"),
            "exchange_order_id": identity.get("broker_order_id") or identity.get("exchange_order_id"),
            "protection": protection_confirmed,
            "disaster_stop_order_id": stop_order_id or None,
            "lifecycle_terminal": str(manager_snapshot.get("state") or "").upper() in {
                "OUTCOME_RECORDED", "LEARNING_ELIGIBLE",
            },
            "close_confirmed": bool(
                isinstance(manager_snapshot.get("close"), Mapping)
                and manager_snapshot.get("close", {}).get("confirmed") is True
            ),
            "outcome_recorded": bool(
                isinstance(manager_snapshot.get("outcome"), Mapping)
                and manager_snapshot.get("outcome", {}).get("confirmed") is True
                and manager_snapshot.get("outcome_id")
            ),
            "quantity_closed": manager_snapshot.get("quantity_closed"),
            "closed_at": (
                manager_snapshot.get("close", {}).get("closed_at")
                if isinstance(manager_snapshot.get("close"), Mapping) else None
            ),
            "close_reason": (
                manager_snapshot.get("close", {}).get("close_reason")
                if isinstance(manager_snapshot.get("close"), Mapping) else None
            ),
        }
        timestamp = _now()
        return {
            "timestamp": timestamp,
            "occurred_at": timestamp,
            "event_id": f"CENTRAL-SHADOW-VALIDATED-{digest}",
            "event_type": "SHADOW_VALIDATED",
            "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
            "status": "MATCH",
            "comparison_status": "MATCH",
            "trade_id": identity.get("trade_id"),
            "registry_id": identity.get("registry_id"),
            "lifecycle_id": lifecycle_id,
            "decision_id": identity.get("decision_id"),
            "signal_id": identity.get("signal_id"),
            "client_order_id": identity.get("client_order_id"),
            "broker_order_id": identity.get("broker_order_id") or identity.get("exchange_order_id") or identity.get("order_id"),
            "broker_stop_order_id": (
                identity.get("broker_stop_order_id") or identity.get("disaster_stop_order_id")
            ) if registry_status == "OPEN" else None,
            "mode": mode,
            "registry_status": registry_status,
            "validated_fields": validated_fields,
            "validated_values": {key: validated_values.get(key) for key in validated_fields},
            "compared_fields": int(comparison.get("compared_fields") or 0),
            "matching_fields": int(comparison.get("matching_fields") or 0),
            "differences": [],
            "shadow_mode": True,
            "fail_open": True,
            "operational_result_preserved": True,
            "operational_authority": False,
            "production_blocked": False,
        }

    @staticmethod
    def _comparison_is_valid_match(
        comparison: Mapping[str, Any],
        original: Mapping[str, Any],
        manager_snapshot: Mapping[str, Any],
    ) -> bool:
        compared = int(comparison.get("compared_fields") or 0)
        matching = int(comparison.get("matching_fields") or 0)
        base_match = (
            str(comparison.get("status") or "").upper() == "MATCH"
            and comparison.get("ok") is True
            and compared >= 7
            and matching == compared
            and not (comparison.get("differences") or [])
        )
        if not base_match:
            return False
        required_identity = (
            _first(original, ("trade_id", "canonical_trade_id")),
            _first(original, ("bot",)),
            _first(original, ("setup",)),
            _first(original, ("symbol",)),
            _first(original, ("side",)),
        )
        mode = _upper_first(original, ("mode", "execution_mode", "registry_mode"))
        status = _upper_first(original, ("status",))
        if any(value in (None, "") for value in required_identity) or not mode or status not in {"OPEN", "CLOSED"}:
            return False
        if mode not in {"LIVE", "REAL"}:
            return True

        quantity = _registry_open_quantity(original)
        client_order_id = _first(original, ("client_order_id",))
        broker_order_id = _first(original, ("broker_order_id", "exchange_order_id"))
        protection_confirmed, stop_order_id = _registry_protection(original)
        if (
            quantity in (None, "")
            or client_order_id in (None, "")
            or broker_order_id in (None, "")
            or not manager_snapshot
        ):
            return False
        field_pairs = (
            (str(required_identity[0]), str(manager_snapshot.get("trade_id") or "")),
            (str(required_identity[1]).upper(), str(manager_snapshot.get("bot") or "").upper()),
            (str(required_identity[2]).upper(), str(manager_snapshot.get("setup") or "").upper()),
            (_normalized_symbol(required_identity[3]), _normalized_symbol(manager_snapshot.get("symbol"))),
            (_normalized_side(required_identity[4]), _normalized_side(manager_snapshot.get("side"))),
            (_normalized_mode(mode), _normalized_mode(manager_snapshot.get("mode"))),
            (str(client_order_id), str(manager_snapshot.get("client_order_id") or "")),
            (str(broker_order_id), str(manager_snapshot.get("exchange_order_id") or "")),
        )
        if any(left != right for left, right in field_pairs):
            return False
        if not _numbers_match(quantity, manager_snapshot.get("quantity_open")):
            return False
        for field in ("lifecycle_id", "decision_id", "signal_id"):
            expected = _first(original, (field,))
            if expected not in (None, "") and str(expected) != str(manager_snapshot.get(field) or ""):
                return False
        if status == "CLOSED":
            close = manager_snapshot.get("close") if isinstance(manager_snapshot.get("close"), Mapping) else {}
            outcome = manager_snapshot.get("outcome") if isinstance(manager_snapshot.get("outcome"), Mapping) else {}
            closed_at = _first(original, ("closed_at",))
            close_reason = _first(original, ("close_reason", "exit_reason", "reason"))
            factual_close = _registry_close_evidence(original)
            expected_outcome = TradeLifecycleShadowRuntimeAdapter._outcome_from_registry(original, factual_close or {})
            outcome_fields_match = True
            for field, aliases in {
                "result_pct": ("result_pct", "pnl_pct"),
                "result_r": ("result_r", "pnl_r"),
                "pnl_usdt": ("pnl_usdt", "realized_pnl"),
                "exit_price": ("exit_price",),
            }.items():
                registry_value = _first(original, aliases)
                if registry_value in (None, ""):
                    continue
                shadow_value = outcome.get(field)
                if isinstance(registry_value, (int, float)) or isinstance(shadow_value, (int, float)):
                    if not _numbers_match(registry_value, shadow_value):
                        outcome_fields_match = False
                        break
                elif str(registry_value) != str(shadow_value or ""):
                    outcome_fields_match = False
                    break
            return bool(
                factual_close is not None
                and
                _numbers_match(manager_snapshot.get("quantity_open"), 0)
                and _positive_float(manager_snapshot.get("quantity_closed")) is not None
                and _numbers_match(manager_snapshot.get("quantity_closed"), factual_close.get("closed_quantity"))
                and _numbers_match(close.get("quantity_confirmed"), factual_close.get("final_close_quantity"))
                and str(manager_snapshot.get("state") or "").upper() in {"OUTCOME_RECORDED", "LEARNING_ELIGIBLE"}
                and close.get("confirmed") is True
                and close.get("factual_registry_close") is True
                and str(close.get("closed_at") or "") == str(closed_at or "")
                and str(close.get("close_reason") or "") == str(close_reason or "")
                and outcome.get("confirmed") is True
                and str(manager_snapshot.get("outcome_id") or "") == str(expected_outcome.get("outcome_id") or "")
                and outcome_fields_match
            )

        current_stop_confirmed, current_stop_order_id = _manager_current_stop(manager_snapshot)
        protected_state = str(manager_snapshot.get("state") or "").upper() in {
            "ENTRY_PROTECTED", "POSITION_MANAGED", "TP50_PENDING", "TP50_CONFIRMED",
            "RUNNER_PROTECTED", "BREAK_EVEN_PENDING", "BREAK_EVEN_ACTIVE",
            "TRAILING_PENDING", "TRAILING_ACTIVE", "CLOSE_PENDING", "CLOSE_PARTIALLY_CONFIRMED",
        }
        return bool(
            protected_state
            and protection_confirmed
            and stop_order_id
            and current_stop_confirmed
            and current_stop_order_id == stop_order_id
        )

    @staticmethod
    def _registry_live_reconciliation_readiness(
        original: Mapping[str, Any],
        manager_snapshot: Mapping[str, Any],
    ) -> tuple[bool, str, list[str]]:
        """Gate LIVE comparison until the Shadow lifecycle is factually complete."""
        source = _upper_first(original, ("source_component",))
        mode = _normalized_mode(_upper_first(original, ("mode", "execution_mode", "registry_mode")))
        if source != "TRADE_REGISTRY" or mode != "LIVE":
            return True, "READY", []

        status = _upper_first(original, ("status",))
        if not _explicit_live_registry_allow(original, statuses={status}) or status not in {"OPEN", "CLOSED"}:
            return False, "INSUFFICIENT_EVIDENCE", ["authoritative Registry LIVE eligibility is incomplete"]
        if not manager_snapshot:
            return False, "LIFECYCLE_INCOMPLETE", ["shadow lifecycle has not been reconstructed"]

        reasons: list[str] = []
        expected_identity = {
            "trade_id": str(_first(original, ("trade_id",)) or ""),
            "bot": str(_first(original, ("bot",)) or "").upper(),
            "setup": str(_first(original, ("setup",)) or "").upper(),
            "symbol": _normalized_symbol(_first(original, ("symbol",))),
            "side": _normalized_side(_first(original, ("side",))),
        }
        actual_identity = {
            "trade_id": str(manager_snapshot.get("trade_id") or ""),
            "bot": str(manager_snapshot.get("bot") or "").upper(),
            "setup": str(manager_snapshot.get("setup") or "").upper(),
            "symbol": _normalized_symbol(manager_snapshot.get("symbol")),
            "side": _normalized_side(manager_snapshot.get("side")),
        }
        for field, expected in expected_identity.items():
            if not expected or expected != actual_identity[field]:
                reasons.append(f"{field} identity is missing or mismatched")

        client_order_id = _first(original, ("client_order_id",))
        exchange_order_id = _first(original, ("broker_order_id", "exchange_order_id"))
        if not client_order_id or str(client_order_id) != str(manager_snapshot.get("client_order_id") or ""):
            reasons.append("client_order_id is missing or mismatched")
        if not exchange_order_id or str(exchange_order_id) != str(manager_snapshot.get("exchange_order_id") or ""):
            reasons.append("exchange_order_id is missing or mismatched")

        state = str(manager_snapshot.get("state") or "").upper()
        if status == "OPEN":
            expected_quantity = _first(original, (
                "remaining_quantity", "remaining_qty", "quantity_open", "open_qty", "quantity", "qty",
            ))
            protected_states = {
                "ENTRY_PROTECTED", "POSITION_MANAGED", "TP50_PENDING", "TP50_CONFIRMED",
                "RUNNER_PROTECTED", "BREAK_EVEN_PENDING", "BREAK_EVEN_ACTIVE",
                "TRAILING_PENDING", "TRAILING_ACTIVE", "CLOSE_PENDING", "CLOSE_PARTIALLY_CONFIRMED",
            }
            entry = manager_snapshot.get("entry_confirmation") if isinstance(manager_snapshot.get("entry_confirmation"), Mapping) else {}
            current_stop_confirmed, current_stop_order_id = _manager_current_stop(manager_snapshot)
            factual_stop = _registry_stop_evidence(original)
            if entry.get("confirmed") is not True:
                reasons.append("factual Registry LIVE entry is not confirmed in Shadow")
            if state not in protected_states:
                reasons.append("shadow lifecycle has not reached a protected OPEN state")
            if expected_quantity in (None, "") or not _numbers_match(expected_quantity, manager_snapshot.get("quantity_open")):
                reasons.append("open quantity is missing or mismatched")
            if factual_stop is None or not current_stop_confirmed:
                reasons.append("physical disaster stop evidence is incomplete")
            elif current_stop_order_id != str(factual_stop.get("order_id") or ""):
                reasons.append("physical disaster stop order is mismatched")
        else:
            close = manager_snapshot.get("close") if isinstance(manager_snapshot.get("close"), Mapping) else {}
            outcome = manager_snapshot.get("outcome") if isinstance(manager_snapshot.get("outcome"), Mapping) else {}
            factual_close = _registry_close_evidence(original)
            if factual_close is None:
                reasons.append("factual Registry LIVE close evidence is incomplete")
            if state not in {"OUTCOME_RECORDED", "LEARNING_ELIGIBLE"}:
                reasons.append("shadow lifecycle has not recorded its outcome")
            if close.get("confirmed") is not True or close.get("factual_registry_close") is not True:
                reasons.append("factual close is not confirmed in Shadow")
            if outcome.get("confirmed") is not True or not manager_snapshot.get("outcome_id"):
                reasons.append("outcome is not confirmed in Shadow")
            if not _numbers_match(manager_snapshot.get("quantity_open"), 0):
                reasons.append("closed lifecycle retains open quantity")
            if _positive_float(manager_snapshot.get("quantity_closed")) is None:
                reasons.append("closed lifecycle has no positive closed quantity")
            if factual_close is not None:
                expected_outcome = TradeLifecycleShadowRuntimeAdapter._outcome_from_registry(original, factual_close)
                if not _numbers_match(
                    manager_snapshot.get("quantity_closed"),
                    factual_close.get("closed_quantity"),
                ):
                    reasons.append("closed quantity is mismatched")
                if not _numbers_match(
                    close.get("quantity_confirmed"),
                    factual_close.get("final_close_quantity"),
                ):
                    reasons.append("final close quantity is missing or mismatched")
                if str(close.get("closed_at") or "") != str(factual_close.get("closed_at") or ""):
                    reasons.append("closed_at is missing or mismatched")
                if str(close.get("close_reason") or "") != str(factual_close.get("close_reason") or ""):
                    reasons.append("close_reason is missing or mismatched")
                if str(manager_snapshot.get("outcome_id") or "") != str(expected_outcome.get("outcome_id") or ""):
                    reasons.append("outcome identity is missing or mismatched")
                for field in ("result_pct", "result_r", "pnl_usdt", "exit_price"):
                    expected = expected_outcome.get(field)
                    if expected in (None, ""):
                        continue
                    actual = outcome.get(field)
                    if not _numbers_match(expected, actual):
                        reasons.append(f"outcome {field} is missing or mismatched")

        return (not reasons), ("READY" if not reasons else "LIFECYCLE_INCOMPLETE"), reasons

    def _append_event_once(self, event: Mapping[str, Any]) -> bool:
        event_id = str(event.get("event_id") or "")
        path_key = str(self.events_file.resolve())
        with _storage_lock(self.events_file):
            lock_file = self.events_file.with_suffix(self.events_file.suffix + ".lock")
            with _cross_process_file_lock(lock_file):
                known = _VALIDATION_EVENT_IDS.setdefault(path_key, set())
                # Re-read under the process lock so another worker's append is
                # visible even after this process initialized its local index.
                if self.events_file.exists():
                    with self.events_file.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            try:
                                row = json.loads(line)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue
                            if isinstance(row, Mapping) and row.get("event_type") == "SHADOW_VALIDATED" and row.get("event_id"):
                                known.add(str(row["event_id"]))
                if event_id in known:
                    return False
                self._append(self.events_file, event)
                known.add(event_id)
                return True

    def _apply_live_sequence(
        self,
        lifecycle_id: str,
        original: Mapping[str, Any],
        steps: Iterable[tuple[str, Mapping[str, Any]]],
        *,
        persist: bool,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        fallback_occurred_at = _first(original, ("occurred_at", "timestamp", "last_update", "updated_at", "opened_at")) or _now()
        transition: Dict[str, Any] = {
            "eligible": True,
            "attempted": True,
            "operational_authority": False,
            "steps": [],
        }
        last_result: Dict[str, Any] = {
            "ok": True,
            "event_applied": False,
            "duplicate": False,
            "blocked": False,
            "status": "NO_STEPS",
        }
        for event_type, evidence in steps:
            occurred_at = _first(evidence, (
                "occurred_at", "timestamp", "confirmed_at", "submitted_at",
                "opened_at", "closed_at",
            )) or fallback_occurred_at
            item = _live_event(lifecycle_id, event_type, occurred_at, evidence)
            last_result = self.manager.apply_event(lifecycle_id, item, persist=persist)
            transition["steps"].append({
                "event_type": event_type,
                "event_id": item["event_id"],
                "manager_result": _manager_result_summary(last_result),
            })
            if not last_result.get("ok") and not last_result.get("duplicate"):
                break
        transition["state_after"] = last_result.get("current_state")
        transition["complete"] = bool(last_result.get("ok") or last_result.get("duplicate"))
        return copy.deepcopy(last_result), transition

    def _manager_snapshot(self, lifecycle_id: str) -> Dict[str, Any]:
        getter = getattr(self.manager, "get_lifecycle", None)
        if not callable(getter):
            return {}
        result = getter(lifecycle_id)
        return copy.deepcopy(result.get("snapshot") or {}) if isinstance(result, dict) else {}

    @staticmethod
    def _live_result_noop(snapshot: Mapping[str, Any], status: str, *, duplicate: bool = False, reason: str = "") -> Dict[str, Any]:
        return {
            "ok": True,
            "status": status,
            "event_applied": False,
            "duplicate": duplicate,
            "blocked": False,
            "reasons": [reason] if reason else [],
            "current_state": snapshot.get("state"),
            "lifecycle_id": snapshot.get("lifecycle_id"),
            "trade_id": snapshot.get("trade_id"),
            "snapshot": copy.deepcopy(dict(snapshot)),
        }

    def _apply_live_fact_steps(
        self,
        lifecycle_id: str,
        original: Mapping[str, Any],
        steps: Iterable[tuple[str, Mapping[str, Any]]],
        *,
        persist: bool,
        transition: Dict[str, Any],
    ) -> Dict[str, Any]:
        step_list = list(steps)
        if not step_list:
            snapshot = self._manager_snapshot(lifecycle_id)
            return self._live_result_noop(snapshot, "LIVE_FACT_ALREADY_OBSERVED", duplicate=True)
        result, partial = self._apply_live_sequence(
            lifecycle_id,
            original,
            step_list,
            persist=persist,
        )
        transition.setdefault("steps", []).extend(partial.get("steps") or [])
        transition["attempted"] = True
        transition["eligible"] = True
        transition["state_after"] = partial.get("state_after")
        transition["complete"] = partial.get("complete")
        return result

    def _advance_live_decision_and_submission(
        self,
        lifecycle_id: str,
        original: Mapping[str, Any],
        *,
        persist: bool,
        transition: Dict[str, Any],
    ) -> Dict[str, Any]:
        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        last = self._live_result_noop(snapshot, "LIVE_DECISION_ALREADY_OBSERVED", duplicate=True)
        decision_states = {"SIGNAL_DETECTED", "DECISION_PENDING", "DECISION_ALLOWED", "RISK_PENDING"}
        if state in decision_states:
            decision = _nested_mapping(original, "execution_decision")
            evidence = {
                "trade_id": str(_first(original, ("trade_id",)) or ""),
                "decision_id": str(_first(original, ("decision_id",)) or ""),
                "mode": "LIVE",
                "registry_source_component": "TRADE_REGISTRY",
                "decision": "ALLOW",
                "timestamp": _first(decision, ("occurred_at", "decided_at", "timestamp"))
                or _first(original, ("signal_at", "created_at", "opened_at", "last_update")),
            }
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                _pending_live_decision_steps(state, evidence),
                persist=persist,
                transition=transition,
            )
            if not last.get("ok") and not last.get("duplicate"):
                return last

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        submission = _live_submission_evidence(original)
        if state == "RISK_APPROVED" and submission is not None:
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("ENTRY_INTENT_CREATED", submission), ("ENTRY_SUBMITTED", submission)),
                persist=persist,
                transition=transition,
            )
        return last

    def _advance_live_entry_and_stop(
        self,
        lifecycle_id: str,
        original: Mapping[str, Any],
        *,
        persist: bool,
        transition: Dict[str, Any],
    ) -> Dict[str, Any]:
        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        last = self._live_result_noop(snapshot, "LIVE_ENTRY_FACT_NOT_READY")
        entry = _registry_entry_evidence(original)
        if state == "ENTRY_SUBMITTING" and entry is not None:
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("ENTRY_CONFIRMED", entry),),
                persist=persist,
                transition=transition,
            )
            if not last.get("ok") and not last.get("duplicate"):
                return last

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        stop = _registry_stop_evidence(original)
        initial_stop_states = {"ENTRY_CONFIRMED", "ENTRY_CONFIRMED_STOP_MISSING", "RECOVERY_REQUIRED"}
        managed_stop_states = {
            "ENTRY_PROTECTED", "POSITION_MANAGED", "TP50_CONFIRMED",
            "RUNNER_PROTECTED", "BREAK_EVEN_ACTIVE", "TRAILING_ACTIVE",
        }
        should_apply_stop = bool(
            stop is not None
            and (
                state in initial_stop_states
                or (
                    state in managed_stop_states
                    and _numbers_match(stop.get("protected_quantity"), snapshot.get("quantity_open"))
                    and _should_refresh_manager_stop(snapshot, stop)
                )
            )
        )
        if should_apply_stop:
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("DISASTER_STOP_CONFIRMED", stop),),
                persist=persist,
                transition=transition,
            )
        elif state == "ENTRY_CONFIRMED":
            stop_failure = _registry_initial_stop_failure(original)
            if stop_failure is not None:
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    (("DISASTER_STOP_FAILED", stop_failure), ("RECOVERY_REQUESTED", stop_failure)),
                    persist=persist,
                    transition=transition,
                )
        return last

    def _advance_live_management(
        self,
        lifecycle_id: str,
        original: Mapping[str, Any],
        *,
        persist: bool,
        transition: Dict[str, Any],
    ) -> Dict[str, Any]:
        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        failure = _registry_stop_update_failure(original)
        if failure is not None and str(failure.get("reason") or "").upper() != "TP50_RESIZE":
            last = self._live_result_noop(snapshot, "STOP_UPDATE_FAILURE_OBSERVED")
            if state == "ENTRY_PROTECTED":
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    (("POSITION_MANAGEMENT_STARTED", {
                        "trade_id": snapshot.get("trade_id"),
                        "registry_source_component": "TRADE_REGISTRY",
                    }),),
                    persist=persist,
                    transition=transition,
                )
                if not last.get("ok") and not last.get("duplicate"):
                    return last
            snapshot = self._manager_snapshot(lifecycle_id)
            state = str(snapshot.get("state") or "").upper()
            reason = str(failure.get("reason") or "").upper()
            request_event = None
            if reason == "BREAK_EVEN" and state in {"POSITION_MANAGED", "RUNNER_PROTECTED", "BREAK_EVEN_ACTIVE"}:
                request_event = "BREAK_EVEN_REQUESTED"
            elif reason == "TRAILING" and state in {"POSITION_MANAGED", "RUNNER_PROTECTED", "BREAK_EVEN_ACTIVE", "TRAILING_ACTIVE"}:
                request_event = "TRAILING_REQUESTED"
            if request_event:
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    ((request_event, failure),),
                    persist=persist,
                    transition=transition,
                )
                if not last.get("ok") and not last.get("duplicate"):
                    return last
            snapshot = self._manager_snapshot(lifecycle_id)
            state = str(snapshot.get("state") or "").upper()
            if state in {"TP50_CONFIRMED", "BREAK_EVEN_PENDING", "TRAILING_PENDING"}:
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    (("RECOVERY_REQUESTED", failure),),
                    persist=persist,
                    transition=transition,
                )
            return last

        tp50 = _registry_tp50_evidence(original)
        if isinstance(snapshot.get("tp50"), Mapping) and snapshot.get("tp50", {}).get("confirmed") is True:
            tp50 = None
        break_even = _registry_stop_management(original, "BREAK_EVEN")
        trailing = _registry_stop_management(original, "TRAILING")
        if not any((tp50, break_even, trailing)):
            return self._live_result_noop(snapshot, "NO_FACTUAL_MANAGEMENT_EVENT")
        last = self._live_result_noop(snapshot, "MANAGEMENT_ALREADY_OBSERVED", duplicate=True)
        if state == "ENTRY_PROTECTED":
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("POSITION_MANAGEMENT_STARTED", {"trade_id": snapshot.get("trade_id"), "registry_source_component": "TRADE_REGISTRY"}),),
                persist=persist,
                transition=transition,
            )
            if not last.get("ok") and not last.get("duplicate"):
                return last

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        if tp50 is not None and state == "POSITION_MANAGED":
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("TP50_REQUESTED", tp50), ("TP50_FILL_RECORDED", tp50), ("TP50_CONFIRMED", tp50)),
                persist=persist,
                transition=transition,
            )
            if not last.get("ok") and not last.get("duplicate"):
                return last
            snapshot = self._manager_snapshot(lifecycle_id)
            state = str(snapshot.get("state") or "").upper()
            stop = _registry_stop_evidence(original)
            if state == "TP50_CONFIRMED" and _positive_float(snapshot.get("quantity_open")) is not None and stop is not None:
                runner = {**stop, "protected_quantity": snapshot.get("quantity_open")}
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    (("RUNNER_PROTECTION_CONFIRMED", runner),),
                    persist=persist,
                    transition=transition,
                )

        # Runner protection may be persisted by Registry in a later update than
        # the TP50 reduction.  Observe that independent factual arrival too.
        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        if state == "TP50_CONFIRMED" and _positive_float(snapshot.get("quantity_open")) is not None:
            stop = _registry_stop_evidence(original)
            if stop is not None:
                runner = {**stop, "protected_quantity": snapshot.get("quantity_open")}
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    (("RUNNER_PROTECTION_CONFIRMED", runner),),
                    persist=persist,
                    transition=transition,
                )

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        if failure is not None and state == "TP50_CONFIRMED":
            return self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("RECOVERY_REQUESTED", failure),),
                persist=persist,
                transition=transition,
            )

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        if break_even is not None and state in {"POSITION_MANAGED", "RUNNER_PROTECTED"}:
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("BREAK_EVEN_REQUESTED", break_even), ("BREAK_EVEN_CONFIRMED", break_even)),
                persist=persist,
                transition=transition,
            )

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        if trailing is not None and state in {"POSITION_MANAGED", "RUNNER_PROTECTED", "BREAK_EVEN_ACTIVE", "TRAILING_ACTIVE"}:
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("TRAILING_REQUESTED", trailing), ("TRAILING_CONFIRMED", trailing)),
                persist=persist,
                transition=transition,
            )
        return last

    @staticmethod
    def _outcome_from_registry(record: Mapping[str, Any], close: Mapping[str, Any]) -> Dict[str, Any]:
        outcome = {
            "result_pct": _first(record, ("result_pct", "pnl_pct")),
            "result_r": _first(record, ("result_r", "pnl_r")),
            "pnl_usdt": _first(record, ("pnl_usdt", "realized_pnl")),
            "exit_reason": close.get("close_reason"),
            "opened_at": _first(record, ("opened_at",)),
            "closed_at": close.get("closed_at"),
            "entry_price_confirmed": _first(record, (
                "entry_price_confirmed", "executed_price", "average_price", "fill_price", "average",
            )),
            "entry_price_reference": _first(record, ("broker_entry_reference",)),
            "entry_price_theoretical": _first(record, ("entry_price_theoretical", "entry_price", "entry")),
            "exit_price": close.get("exit_price"),
            "initial_quantity": _registry_quantity(record),
            "closed_quantity": close.get("closed_quantity"),
            "final_close_quantity": close.get("final_close_quantity"),
            "mode": "LIVE",
            "bot": _first(record, ("bot",)),
            "setup": _first(record, ("setup",)),
        }
        material = {
            "schema": "CENTRAL_SHADOW_OUTCOME_V1",
            "trade_id": _first(record, ("trade_id",)),
            "closed_at": close.get("closed_at"),
            "close_reason": close.get("close_reason"),
            "result_pct": outcome.get("result_pct"),
            "result_r": outcome.get("result_r"),
            "pnl_usdt": outcome.get("pnl_usdt"),
            "exit_price": outcome.get("exit_price"),
            "closed_quantity": outcome.get("closed_quantity"),
        }
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32].upper()
        return {"outcome_id": f"CENTRAL-SHADOW-OUTCOME-{digest}", **{key: value for key, value in outcome.items() if value not in (None, "")}}

    def _advance_live_close_and_outcome(
        self,
        lifecycle_id: str,
        original: Mapping[str, Any],
        *,
        persist: bool,
        transition: Dict[str, Any],
    ) -> Dict[str, Any]:
        close = _registry_close_evidence(original)
        snapshot = self._manager_snapshot(lifecycle_id)
        if close is None:
            return self._live_result_noop(snapshot, "FACTUAL_REGISTRY_CLOSE_INCOMPLETE")
        state = str(snapshot.get("state") or "").upper()
        closable = {
            "ENTRY_CONFIRMED_STOP_MISSING", "ENTRY_PROTECTED", "POSITION_MANAGED", "RUNNER_PROTECTED",
            "TP50_PENDING", "TP50_CONFIRMED", "BREAK_EVEN_PENDING", "BREAK_EVEN_ACTIVE",
            "TRAILING_PENDING", "TRAILING_ACTIVE", "RECOVERY_REQUIRED", "CLOSE_PARTIALLY_CONFIRMED",
        }
        last = self._live_result_noop(snapshot, "REGISTRY_CLOSE_ALREADY_OBSERVED", duplicate=True)
        if state in closable:
            if state != "CLOSE_PARTIALLY_CONFIRMED":
                last = self._apply_live_fact_steps(
                    lifecycle_id,
                    original,
                    (("CLOSE_REQUESTED", close),),
                    persist=persist,
                    transition=transition,
                )
                if not last.get("ok") and not last.get("duplicate"):
                    return last
            last = self._apply_live_fact_steps(
                lifecycle_id,
                original,
                (("CLOSE_CONFIRMED", close),),
                persist=persist,
                transition=transition,
            )
            if not last.get("ok") and not last.get("duplicate"):
                return last

        snapshot = self._manager_snapshot(lifecycle_id)
        state = str(snapshot.get("state") or "").upper()
        if state in {"CLOSE_CONFIRMED", "OUTCOME_PENDING"}:
            outcome = self._outcome_from_registry(original, close)
            result = self.manager.record_outcome(lifecycle_id, outcome, persist=persist)
            transition.setdefault("steps", []).append({
                "event_type": "OUTCOME_RECORDED",
                "event_id": outcome["outcome_id"],
                "manager_result": _manager_result_summary(result),
            })
            transition["attempted"] = True
            transition["state_after"] = result.get("current_state")
            return result
        return last

    def _observe_registry_live(
        self,
        canonical: str,
        original: Mapping[str, Any],
        lifecycle_id: str,
        identity: Mapping[str, str],
        event_id: str,
        *,
        persist: bool,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        transition: Dict[str, Any] = {
            "source_event_type": canonical,
            "eligible": False,
            "attempted": False,
            "operational_authority": False,
            "reason": None,
            "steps": [],
        }
        status = _upper_first(original, ("status",))
        eligible = _explicit_live_registry_allow(original, statuses={status}) and status in {"OPEN", "CLOSED"}
        if not eligible:
            transition["reason"] = "REGISTRY_LIVE_ELIGIBILITY_FAILED"
            return self._live_result_noop({}, "NOT_ELIGIBLE", reason=transition["reason"]), transition

        snapshot = self._manager_snapshot(lifecycle_id)
        result = self._live_result_noop(snapshot, "LIVE_FACT_ALREADY_OBSERVED", duplicate=bool(snapshot))
        if not snapshot:
            if status != "OPEN" or canonical not in {"SIGNAL_CREATED", "TRADE_UPDATED"}:
                transition["reason"] = "LIFECYCLE_NOT_FOUND"
                return {
                    "ok": False, "status": "LIFECYCLE_NOT_FOUND", "event_applied": False,
                    "duplicate": False, "blocked": True, "reasons": ["live close arrived before lifecycle creation"],
                    "snapshot": {}, "current_state": "",
                }, transition
            create_payload = copy.deepcopy(dict(original))
            create_payload.update({"lifecycle_id": lifecycle_id, "trade_id": identity["value"], "mode": "LIVE"})
            create_payload.setdefault("event_id", event_id)
            decision = _nested_mapping(original, "execution_decision")
            create_payload.setdefault(
                "occurred_at",
                _first(original, ("signal_at", "created_at"))
                or _first(decision, ("occurred_at", "decided_at", "timestamp"))
                or _first(original, ("opened_at", "last_update"))
                or _now(),
            )
            if create_payload.get("quantity_planned") in (None, ""):
                create_payload["quantity_planned"] = _registry_quantity(original) or 0.0
            if create_payload.get("entry_price_theoretical") in (None, ""):
                create_payload["entry_price_theoretical"] = _first(original, ("entry_price", "entry"))
            created = self.manager.create_lifecycle(create_payload, persist=persist)
            transition["lifecycle_create"] = _manager_result_summary(created)
            if not created.get("ok") and not created.get("duplicate"):
                return created, transition
            result = copy.deepcopy(created)

        transition["eligible"] = True
        transition["reason"] = None
        candidate = self._advance_live_decision_and_submission(
            lifecycle_id, original, persist=persist, transition=transition,
        )
        if not candidate.get("ok") and not candidate.get("duplicate"):
            return candidate, transition
        if candidate.get("event_applied") or candidate.get("blocked") or not result.get("event_applied"):
            result = candidate
        candidate = self._advance_live_entry_and_stop(
            lifecycle_id, original, persist=persist, transition=transition,
        )
        if not candidate.get("ok") and not candidate.get("duplicate"):
            return candidate, transition
        if candidate.get("event_applied") or candidate.get("blocked") or not result.get("event_applied"):
            result = candidate
        management = self._advance_live_management(
            lifecycle_id, original, persist=persist, transition=transition,
        )
        if management.get("event_applied") or management.get("blocked"):
            result = management
        # TP50 may reduce quantity before its replacement stop can satisfy the
        # per-lifecycle quantity invariant. Re-evaluate that same factual stop
        # only after management has recorded the reduction.
        refreshed_stop = self._advance_live_entry_and_stop(
            lifecycle_id, original, persist=persist, transition=transition,
        )
        if refreshed_stop.get("event_applied") or refreshed_stop.get("blocked"):
            result = refreshed_stop
        if status == "CLOSED":
            result = self._advance_live_close_and_outcome(
                lifecycle_id, original, persist=persist, transition=transition,
            )
        final = self._manager_snapshot(lifecycle_id)
        transition["state_after"] = final.get("state")
        transition["complete"] = bool(final)
        if result.get("status") in {
            "LIVE_ENTRY_FACT_NOT_READY", "NO_FACTUAL_MANAGEMENT_EVENT",
            "LIVE_FACT_ALREADY_OBSERVED", "LIVE_DECISION_ALREADY_OBSERVED",
        }:
            if transition.get("steps"):
                result = self._live_result_noop(final, "LIVE_FACTS_OBSERVED")
            else:
                result = self._live_result_noop(
                    final,
                    "INSUFFICIENT_EVIDENCE",
                    reason="no new factual Registry LIVE lifecycle evidence",
                )
        return result, transition

    @staticmethod
    def _paper_open_skip_reason(original: Mapping[str, Any], external: bool, identity: Mapping[str, str], lifecycle_id: str, create_result: Mapping[str, Any]) -> Optional[str]:
        if external:
            return "EXTERNAL_OR_MANUAL_POSITION"
        if _upper_first(original, ("source_component",)) != "TRADE_REGISTRY":
            return "SOURCE_IS_NOT_TRADE_REGISTRY"
        if _upper_first(original, ("mode", "execution_mode", "registry_mode")) != "PAPER":
            return "MODE_IS_NOT_PAPER"
        if _upper_first(original, ("status",)) != "OPEN":
            return "REGISTRY_STATUS_IS_NOT_OPEN"
        supplied_trade_id = str(_first(original, ("trade_id", "canonical_trade_id")) or "").strip()
        if not supplied_trade_id or supplied_trade_id != str(identity.get("value") or ""):
            return "TRADE_ID_MISSING_OR_MISMATCHED"
        if not lifecycle_id:
            return "LIFECYCLE_ID_MISSING"
        if not create_result.get("ok") or not create_result.get("event_applied") or create_result.get("duplicate"):
            return "LIFECYCLE_NOT_NEWLY_CREATED"
        snapshot = create_result.get("snapshot") if isinstance(create_result.get("snapshot"), Mapping) else {}
        if str(snapshot.get("lifecycle_id") or "") != lifecycle_id or str(snapshot.get("trade_id") or "") != supplied_trade_id:
            return "CREATED_LIFECYCLE_IDENTITY_MISMATCH"
        if snapshot.get("state") != "SIGNAL_DETECTED" or snapshot.get("mode") != "PAPER":
            return "CREATED_LIFECYCLE_STATE_OR_MODE_MISMATCH"
        return None

    @staticmethod
    def _paper_close_skip_reason(original: Mapping[str, Any], external: bool, identity: Mapping[str, str], lifecycle_id: str, snapshot: Mapping[str, Any]) -> Optional[str]:
        if external:
            return "EXTERNAL_OR_MANUAL_POSITION"
        if _upper_first(original, ("source_component",)) != "TRADE_REGISTRY":
            return "SOURCE_IS_NOT_TRADE_REGISTRY"
        if _upper_first(original, ("mode", "execution_mode", "registry_mode")) != "PAPER":
            return "MODE_IS_NOT_PAPER"
        if _upper_first(original, ("status",)) != "CLOSED":
            return "REGISTRY_STATUS_IS_NOT_CLOSED"
        if _first(original, ("closed_at",)) in (None, ""):
            return "CLOSED_AT_MISSING"
        if not any(_first(original, (key,)) not in (None, "") for key in ("exit_price", "close_reason", "pnl_pct", "pnl_r", "result_pct", "result_r")):
            return "PAPER_CLOSE_EVIDENCE_MISSING"
        supplied_trade_id = str(_first(original, ("trade_id", "canonical_trade_id")) or "").strip()
        if not supplied_trade_id or supplied_trade_id != str(identity.get("value") or ""):
            return "TRADE_ID_MISSING_OR_MISMATCHED"
        if not snapshot:
            return "LIFECYCLE_NOT_FOUND"
        if str(snapshot.get("lifecycle_id") or "") != lifecycle_id or str(snapshot.get("trade_id") or "") != supplied_trade_id:
            return "LIFECYCLE_IDENTITY_MISMATCH"
        if snapshot.get("mode") != "PAPER":
            return "LIFECYCLE_MODE_IS_NOT_PAPER"
        if snapshot.get("state") not in {"PAPER_POSITION_OPEN", "CLOSE_CONFIRMED"}:
            return "LIFECYCLE_IS_NOT_PAPER_POSITION_OPEN"
        return None

    def observe_event(self, event_type: str, payload: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
        """Normalize and forward a factual event; never propagate an exception."""
        try:
            if not isinstance(payload, dict):
                return self._result("INVALID_CONTRACT", ok=False, reasons=["payload must be dict"])
            original = copy.deepcopy(payload)
            canonical = LEGACY_EVENT_MAP.get(str(event_type or "").upper().strip(), str(event_type or "").upper().strip())
            if not self.enabled:
                return self._result("DISABLED", forwarded=False, event_type=canonical)
            identity = _canonical_identity(original)
            external = bool(_first(original, ("external_position", "manual_position"))) or canonical == "EXTERNAL_POSITION_DETECTED"
            lifecycle = _resolve_lifecycle_id(original, identity, external=external)
            lifecycle_id = lifecycle["value"]
            if not lifecycle_id:
                return self._result("INSUFFICIENT_IDENTITY", ok=False, forwarded=False, reasons=["canonical trade identity missing"])
            event_id = self._event_id(canonical, identity["value"] or lifecycle_id, original)
            with self._lock:
                self._metrics["observed"] += 1
                manager_event_type = canonical
                paper_transition = {
                    "source_event_type": canonical,
                    "derived_event_type": None,
                    "attempted": False,
                    "applied": False,
                    "status": "NOT_APPLICABLE",
                    "reason": None,
                }
                live_transition: Dict[str, Any] = {
                    "source_event_type": canonical,
                    "eligible": False,
                    "attempted": False,
                    "operational_authority": False,
                    "reason": "NOT_APPLICABLE",
                    "steps": [],
                }
                registry_live_observation = bool(
                    _upper_first(original, ("source_component",)) == "TRADE_REGISTRY"
                    and _normalized_mode(_upper_first(original, ("mode", "execution_mode", "registry_mode"))) == "LIVE"
                    and canonical in {"SIGNAL_CREATED", "TRADE_UPDATED", "CLOSE_CONFIRMED", "OUTCOME_CONFIRMED"}
                )
                registry_non_operational_signal = bool(
                    _upper_first(original, ("source_component",)) == "TRADE_REGISTRY"
                    and canonical == "SIGNAL_CREATED"
                    and _upper_first(original, ("mode", "execution_mode", "registry_mode"))
                    in {"PREVIEW", "VERIFY", "DRY_RUN", "SAFE_DRY_RUN", "OBSERVATION_ONLY"}
                )
                if canonical == "CLOSE_CONFIRMED":
                    current_snapshot = self._manager_snapshot(lifecycle_id)
                    skip_reason = self._paper_close_skip_reason(original, external, identity, lifecycle_id, current_snapshot)
                    paper_transition.update({
                        "status": "SKIPPED" if skip_reason else "ELIGIBLE",
                        "reason": skip_reason,
                        "lifecycle_state_before": current_snapshot.get("state"),
                    })
                    if skip_reason is None:
                        manager_event_type = "PAPER_POSITION_CLOSED"
                        paper_transition["derived_event_type"] = manager_event_type

                key = f"{lifecycle_id}|{manager_event_type}|{event_id}"
                if key in self._seen:
                    self._metrics["duplicate"] += 1
                    return self._result("DUPLICATE", duplicate=True, event_id=event_id, lifecycle_id=lifecycle_id, lifecycle_id_source=lifecycle["source"], identity_source=identity["source"])
                event = {"event_id": event_id, "event_type": manager_event_type, "lifecycle_id": lifecycle_id, "source_component": str(_first(original, ("source_component", "source")) or "SHADOW_RUNTIME_ADAPTER"), "occurred_at": str(_first(original, ("occurred_at", "timestamp", "updated_at", "last_update", "closed_at", "opened_at")) or _now()), "evidence": _json_safe(original.get("evidence") or original), "payload": _json_safe(original)}
                if manager_event_type == "PAPER_POSITION_CLOSED":
                    event = _paper_event(manager_event_type, event_id, lifecycle_id, identity["value"], original)
                    paper_transition.update({"attempted": True, "derived_event_id": event["event_id"]})
                if registry_live_observation:
                    result, live_transition = self._observe_registry_live(
                        canonical,
                        original,
                        lifecycle_id,
                        identity,
                        event_id,
                        persist=persist,
                    )
                    result = copy.deepcopy(result)
                    result["live_position_transition"] = copy.deepcopy(live_transition)
                elif registry_non_operational_signal:
                    result = self._live_result_noop(
                        {},
                        "NOT_ELIGIBLE",
                        reason="Registry preview/verification/dry-run observation does not create lifecycle",
                    )
                elif canonical in {"SIGNAL_CREATED", "EXTERNAL_POSITION_DETECTED"}:
                    create_payload = copy.deepcopy(original)
                    create_payload.update({"lifecycle_id": lifecycle_id, "trade_id": "" if external else identity["value"], "external_position": external, "manual_position": external})
                    create_payload.setdefault("event_id", event_id)
                    create_payload.setdefault("occurred_at", event["occurred_at"])
                    canonical_mode = _first(original, ("mode", "execution_mode", "registry_mode"))
                    if canonical_mode not in (None, ""):
                        create_payload["mode"] = canonical_mode
                    if create_payload.get("quantity_planned") in (None, ""):
                        planned = _first(original, ("initial_quantity", "initial_qty", "original_quantity", "quantity", "qty"))
                        if planned not in (None, ""):
                            create_payload["quantity_planned"] = planned
                    if create_payload.get("entry_price_theoretical") in (None, ""):
                        theoretical = _first(original, ("entry", "entry_price"))
                        if theoretical not in (None, ""):
                            create_payload["entry_price_theoretical"] = theoretical
                    if external:
                        create_payload["bot"] = ""
                        create_payload["setup"] = ""
                        create_payload["signal_id"] = ""
                        create_payload["decision_id"] = ""
                    create_result = self.manager.create_lifecycle(create_payload, persist=persist)
                    skip_reason = self._paper_open_skip_reason(original, external, identity, lifecycle_id, create_result)
                    paper_transition.update({
                        "status": "SKIPPED" if skip_reason else "ELIGIBLE",
                        "reason": skip_reason,
                        "lifecycle_create": _manager_result_summary(create_result),
                    })
                    if skip_reason is None:
                        paper_event = _paper_event("PAPER_POSITION_OPENED", event_id, lifecycle_id, identity["value"], original)
                        paper_transition.update({"attempted": True, "derived_event_type": paper_event["event_type"], "derived_event_id": paper_event["event_id"]})
                        paper_result = self.manager.apply_event(lifecycle_id, paper_event, persist=persist)
                        result = copy.deepcopy(paper_result)
                        result["lifecycle_create"] = _manager_result_summary(create_result)
                        paper_transition.update({
                            "applied": bool(paper_result.get("event_applied")),
                            "status": paper_result.get("status"),
                            "reason": "; ".join(str(item) for item in (paper_result.get("reasons") or [])) or None,
                            "lifecycle_state_after": paper_result.get("current_state"),
                        })
                    else:
                        result = copy.deepcopy(create_result)
                    if not external and _explicit_live_allow(original) and create_result.get("ok"):
                        decision = _nested_mapping(original, "execution_decision")
                        live_evidence = {
                            "trade_id": identity["value"],
                            "decision_id": str(_first(original, ("decision_id",)) or ""),
                            "mode": _upper_first(original, ("mode", "execution_mode", "registry_mode")),
                            "registry_source_component": "TRADE_REGISTRY",
                            "decision": "ALLOW",
                            "timestamp": _first(decision, ("occurred_at", "decided_at", "timestamp"))
                            or _first(original, ("signal_at", "created_at", "opened_at", "last_update")),
                        }
                        live_steps = [
                            ("DECISION_PENDING_RECORDED", live_evidence),
                            ("DECISION_ALLOWED_RECORDED", live_evidence),
                            ("RISK_PENDING_RECORDED", live_evidence),
                            ("RISK_APPROVED_RECORDED", live_evidence),
                        ]
                        result, live_transition = self._apply_live_sequence(
                            lifecycle_id, original, live_steps, persist=persist,
                        )
                        result["lifecycle_create"] = _manager_result_summary(create_result)
                        live_transition["reason"] = None
                    elif not external:
                        live_transition["reason"] = "EXPLICIT_LIVE_ALLOW_NOT_AVAILABLE"
                    result["paper_position_transition"] = copy.deepcopy(paper_transition)
                    result["live_position_transition"] = copy.deepcopy(live_transition)
                elif canonical == "TRADE_UPDATED":
                    submission = _live_submission_evidence(original)
                    if submission is None:
                        result = {"ok": True, "event_applied": False, "duplicate": False, "blocked": False, "status": "NOOP", "warning": "TRADE_UPDATED lacks complete factual LIVE submission evidence"}
                        live_transition["reason"] = "LIVE_SUBMISSION_EVIDENCE_INCOMPLETE"
                    else:
                        steps = []
                        if _explicit_live_allow(original):
                            decision = _nested_mapping(original, "execution_decision")
                            decision_evidence = {
                                "trade_id": identity["value"],
                                "decision_id": str(_first(original, ("decision_id",)) or ""),
                                "mode": submission["mode"],
                                "registry_source_component": "TRADE_REGISTRY",
                                "decision": "ALLOW",
                                "timestamp": _first(decision, ("occurred_at", "decided_at", "timestamp"))
                                or _first(original, ("signal_at", "created_at", "opened_at", "last_update")),
                            }
                            current_snapshot = self._manager_snapshot(lifecycle_id)
                            steps.extend(_pending_live_decision_steps(current_snapshot.get("state"), decision_evidence))
                        steps.extend([
                            ("ENTRY_INTENT_CREATED", submission),
                            ("ENTRY_SUBMITTED", submission),
                        ])
                        result, live_transition = self._apply_live_sequence(
                            lifecycle_id, original, steps, persist=persist,
                        )
                        live_transition["reason"] = None
                    result["live_position_transition"] = copy.deepcopy(live_transition)
                else:
                    result = self.manager.apply_event(lifecycle_id, event, persist=persist)
                    if canonical == "CLOSE_CONFIRMED":
                        paper_transition.update({
                            "applied": bool(result.get("event_applied")),
                            "status": result.get("status"),
                            "reason": paper_transition.get("reason") or "; ".join(str(item) for item in (result.get("reasons") or [])) or None,
                            "lifecycle_state_after": result.get("current_state"),
                        })
                        result = copy.deepcopy(result)
                        result["paper_position_transition"] = copy.deepcopy(paper_transition)
                result_status = str(result.get("status") or "").upper()
                if result.get("duplicate"):
                    self._seen.add(key)
                    self._metrics["duplicate"] += 1
                    status = "DUPLICATE"
                elif result.get("event_applied"):
                    self._seen.add(key)
                    self._metrics["applied"] += 1
                    status = "APPLIED"
                elif result_status in {"NOT_ELIGIBLE", "INSUFFICIENT_EVIDENCE", "LIFECYCLE_INCOMPLETE"}:
                    self._metrics["blocked"] += 1
                    status = result_status
                else:
                    self._metrics["blocked"] += 1
                    status = "BLOCKED"
                journal = {"timestamp": _now(), "event_id": event_id, "event_type": manager_event_type, "source_event_type": canonical, "lifecycle_id": lifecycle_id, "lifecycle_id_source": lifecycle["source"], "identity": identity, "identity_source": identity["source"], "status": status, "paper_position_transition": _json_safe(paper_transition), "live_position_transition": _json_safe(live_transition), "manager_result": _json_safe(result)}
                if persist:
                    self._append(self.events_file, journal)
                    self._persist_state()
                return self._result(
                    status,
                    ok=status in {"APPLIED", "DUPLICATE", "NOT_ELIGIBLE", "INSUFFICIENT_EVIDENCE", "LIFECYCLE_INCOMPLETE"},
                    duplicate=status == "DUPLICATE",
                    forwarded=True,
                    event_id=event_id,
                    lifecycle_id=lifecycle_id,
                    lifecycle_id_source=lifecycle["source"],
                    identity_source=identity["source"],
                    manager_result=result,
                )
        except Exception as exc:
            with self._lock:
                self._metrics["errors"] += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
            LOGGER.warning("shadow runtime adapter observe_event failed: %s", exc)
            return self._result("ERROR", ok=False, forwarded=False, error=self._last_error)

    def reconcile_trade(self, registry_trade: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
        try:
            if not isinstance(registry_trade, dict):
                return self._result("INVALID_CONTRACT", ok=False, reconciled=False, reasons=["registry_trade must be dict"])
            if not self.enabled:
                return self._result("DISABLED", reconciled=False)
            original = copy.deepcopy(registry_trade)
            identity = _canonical_identity(original)
            external = bool(_first(original, ("external_position", "manual_position")))
            lifecycle = _resolve_lifecycle_id(original, identity, external=external)
            lifecycle_id = lifecycle["value"]
            if not lifecycle_id:
                return self._result("INSUFFICIENT_IDENTITY", ok=False, reconciled=False, reasons=["canonical trade identity missing"])
            manager_snapshot = self._manager_snapshot(lifecycle_id)
            ready, readiness_status, readiness_reasons = self._registry_live_reconciliation_readiness(
                original,
                manager_snapshot,
            )
            if not ready:
                return self._result(
                    readiness_status,
                    ok=True,
                    reconciled=False,
                    lifecycle_id=lifecycle_id,
                    lifecycle_id_source=lifecycle["source"],
                    identity_source=identity["source"],
                    reasons=readiness_reasons,
                    comparison=None,
                    shadow_validation={
                        "eligible": False,
                        "persisted": False,
                        "duplicate": False,
                        "event": None,
                        "error": None,
                    },
                )
            comparison = self.manager.compare_with_registry(lifecycle_id, original)
            manager_snapshot = self._manager_snapshot(lifecycle_id)
            with self._lock:
                self._metrics["reconciled"] += 1
                differences = comparison.get("differences") or []
                validation = {
                    "eligible": self._comparison_is_valid_match(comparison, original, manager_snapshot),
                    "persisted": False,
                    "duplicate": False,
                    "event": None,
                    "error": None,
                }
                for difference in differences:
                    key = hashlib.sha256(json.dumps({"lifecycle_id": lifecycle_id, "field": difference.get("field"), "shadow": difference.get("shadow_value"), "registry": difference.get("registry_value")}, sort_keys=True, default=str).encode()).hexdigest()
                    if key in self._divergence_keys:
                        continue
                    self._divergence_keys.add(key)
                    self._metrics["divergences"] += 1
                    if persist:
                        self._append(self.divergences_file, {"timestamp": _now(), "key": key, **difference})
                if validation["eligible"]:
                    event = self._shadow_validation_event(original, lifecycle_id, comparison, manager_snapshot)
                    validation["event"] = copy.deepcopy(event)
                    if persist:
                        try:
                            validation["persisted"] = self._append_event_once(event)
                            validation["duplicate"] = not validation["persisted"]
                        except (OSError, ValueError, TypeError) as exc:
                            self._last_error = f"{type(exc).__name__}: {exc}"
                            validation["error"] = self._last_error
                if persist:
                    try:
                        self._persist_state()
                    except OSError as exc:
                        self._last_error = f"{type(exc).__name__}: {exc}"
                        validation["error"] = validation.get("error") or self._last_error
            return self._result(
                comparison.get("status", "UNKNOWN"),
                ok=True,
                reconciled=True,
                lifecycle_id=lifecycle_id,
                lifecycle_id_source=lifecycle["source"],
                identity_source=identity["source"],
                comparison=comparison,
                shadow_validation=validation,
            )
        except Exception as exc:
            with self._lock:
                self._metrics["errors"] += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
            LOGGER.warning("shadow runtime adapter reconcile_trade failed: %s", exc)
            return self._result("ERROR", ok=False, reconciled=False, error=self._last_error)

    def reconcile_all(self, registry_snapshot: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
        try:
            open_items = registry_snapshot.get("open_trades", {})
            closed_items = registry_snapshot.get("closed_trades", [])
            records = list(open_items.values()) if isinstance(open_items, dict) else list(open_items or [])
            records.extend(list(closed_items or []))
            results = [self.reconcile_trade(item, persist=persist) for item in records if isinstance(item, dict)]
            return self._result("RECONCILED", count=len(results), results=results)
        except Exception as exc:
            return self._result("ERROR", ok=False, error=f"{type(exc).__name__}: {exc}")

    def get_metrics(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return self._result("OK", metrics=copy.deepcopy(self._metrics))
        except Exception as exc:
            return self._result("ERROR", ok=False, error=str(exc))

    def get_health(self) -> Dict[str, Any]:
        try:
            manager_health = self.manager.trade_lifecycle_health()
            return self._result("ENABLED" if self.enabled else "DISABLED", enabled=self.enabled, version=VERSION, operational_authority=False, broker_access=False, registry_write_access=False, last_error=self._last_error, metrics=self.get_metrics().get("metrics", {}), lifecycle_manager_health=manager_health)
        except Exception as exc:
            return self._result("ERROR", ok=False, enabled=self.enabled, version=VERSION, broker_access=False, registry_write_access=False, error=str(exc))


_default_adapter = TradeLifecycleShadowRuntimeAdapter()


def safe_observe_shadow_event(event_type: str, payload: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
    """Stable fail-open entrypoint for runtime producers."""
    return _default_adapter.observe_event(event_type, payload, persist=persist)


def safe_reconcile_shadow_trade(registry_trade: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
    """Read-only best-effort comparison for a Registry-confirmed snapshot."""
    return _default_adapter.reconcile_trade(registry_trade, persist=persist)


def get_shadow_runtime_adapter_health() -> Dict[str, Any]:
    """Return health from the official runtime adapter without mutating it."""
    return _default_adapter.get_health()


def get_shadow_runtime_adapter_metrics() -> Dict[str, Any]:
    """Return metrics from the official runtime adapter without mutating it."""
    return _default_adapter.get_metrics()


__all__ = [
    "TradeLifecycleShadowRuntimeAdapter",
    "safe_observe_shadow_event",
    "safe_reconcile_shadow_trade",
    "get_shadow_runtime_adapter_health",
    "get_shadow_runtime_adapter_metrics",
    "VERSION",
    "MODE",
]
