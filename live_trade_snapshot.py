"""Live Trade Snapshot V1 -- consolidacao manual, observacional e read-only."""

from __future__ import annotations

import copy
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

from trade_timeline_validator import COMPONENTS as TIMELINE_COMPONENTS
from trade_timeline_validator import (
    build_default_sources,
    correlate_source_records,
    new_correlation_context,
    validate_trade_timeline,
)


SNAPSHOT_VERSION = "LIVE_TRADE_SNAPSHOT_V1"
LOGGER = logging.getLogger(__name__)
MAX_TRADE_ID_LENGTH = 256
GRACE_WINDOWS = {
    "broker_ack_grace_seconds": 120,
    "registry_sync_grace_seconds": 120,
    "lifecycle_sync_grace_seconds": 120,
    "close_sync_grace_seconds": 180,
    "telegram_grace_seconds": 300,
}
SOURCE_ORDER = (
    "registry", "lifecycle", "history_manager", "execution_engine",
    "execution_orchestrator", "broker", "shadow_runtime", "timeline",
    "telegram", "falcon", "external_exposure",
)
IDENTITY_KEYS = {
    "trade_id", "trade_uuid", "registry_id", "lifecycle_id", "execution_id",
    "decision_id", "signal_id", "client_order_id", "clientorderid",
    "broker_order_id", "exchange_order_id", "broker_stop_order_id",
    "disaster_stop_order_id", "order_id", "fill_id", "fill_ids",
}
FINAL_EVENTS = {"LIVE_TRADE_CLOSED", "REGISTRY_CLOSE", "LIFECYCLE_FINISHED"}
ENTRY_CONFIRMED_STATES = {
    "ENTRY_CONFIRMED", "ENTRY_CONFIRMED_STOP_MISSING", "ENTRY_PROTECTED",
    "POSITION_MANAGED", "TP50_PENDING", "TP50_CONFIRMED", "RUNNER_PROTECTED",
    "BREAK_EVEN_PENDING", "BREAK_EVEN_ACTIVE", "TRAILING_PENDING",
    "TRAILING_ACTIVE", "CLOSE_PENDING", "CLOSE_PARTIALLY_CONFIRMED",
    "CLOSE_CONFIRMED", "OUTCOME_PENDING", "OUTCOME_RECORDED",
    "LEARNING_ELIGIBLE",
}
PROTECTED_STATES = {
    "ENTRY_PROTECTED", "POSITION_MANAGED", "TP50_PENDING", "TP50_CONFIRMED",
    "RUNNER_PROTECTED", "BREAK_EVEN_PENDING", "BREAK_EVEN_ACTIVE",
    "TRAILING_PENDING", "TRAILING_ACTIVE",
}
CLOSED_LIFECYCLE_STATES = {
    "CLOSE_CONFIRMED", "OUTCOME_PENDING", "OUTCOME_RECORDED",
    "LEARNING_ELIGIBLE",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("trade_id must be text")
    trade_id = value.strip()
    if not trade_id:
        raise ValueError("trade_id is required")
    if len(trade_id) > MAX_TRADE_ID_LENGTH:
        raise ValueError("trade_id is too long")
    if trade_id in {".", ".."} or any(char in trade_id for char in ("/", "\\", "\x00")):
        raise ValueError("trade_id is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in trade_id):
        raise ValueError("trade_id is invalid")
    return trade_id


def _walk(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _identity_values(value: Any) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for item in _walk(value):
        for key, raw in item.items():
            normalized = str(key).lower()
            if normalized in IDENTITY_KEYS and raw not in (None, ""):
                found.setdefault(normalized, str(raw).strip())
    return found


def _records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("records", "items", "events", "lifecycles"):
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, Mapping)]
        if "trade" in value and isinstance(value["trade"], Mapping):
            return [value["trade"]]
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    raw = value.get("_reader_metadata")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _first(records: Iterable[Mapping[str, Any]], *keys: str) -> Any:
    rows = list(records)
    for record in reversed(rows):
        for item in _walk(record):
            for key in keys:
                if item.get(key) not in (None, ""):
                    return item[key]
    return None


def _event_names(records: Iterable[Mapping[str, Any]]) -> list[str]:
    names = []
    for record in records:
        for item in _walk(record):
            raw = item.get("event_type") or item.get("event") or item.get("action")
            if raw not in (None, ""):
                names.append(str(raw).upper().strip().replace(" ", "_"))
    return names


def _confirmed_lifecycle_event(records: Iterable[Mapping[str, Any]], event_type: str) -> bool:
    expected = str(event_type).upper().strip()
    for record in records:
        for item in _walk(record):
            raw = item.get("event_type") or item.get("event") or item.get("action")
            if str(raw or "").upper().strip().replace(" ", "_") != expected:
                continue
            if item.get("applied") is False or _bool(item.get("blocked")):
                continue
            return True
    return False


def _lifecycle_bucket(records: Iterable[Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    rows = list(records)
    for record in reversed(rows):
        containers = [record]
        for key in ("snapshot", "result"):
            value = record.get(key)
            if isinstance(value, Mapping):
                containers.append(value)
        for container in containers:
            value = container.get(name)
            if isinstance(value, Mapping):
                return value
    return {}


def _timestamp_epoch(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000.0 if number > 10_000_000_000 else number
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return _timestamp_epoch(float(text))
    except ValueError:
        pass
    for fmt in (None, "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            continue
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "sim", "on", "confirmed", "active"}
    return bool(value)


def _source_status(value: Any, rows: list[Mapping[str, Any]]) -> str:
    meta = _metadata(value)
    if isinstance(value, Mapping) and value.get("available") is False:
        return "UNAVAILABLE"
    if meta.get("invalid_lines", 0) and not meta.get("valid_lines", 0):
        return "DEGRADED"
    if meta.get("partial") or meta.get("coverage_limited"):
        return "PARTIAL"
    if rows or (isinstance(value, Mapping) and value.get("available") is True):
        return "AVAILABLE"
    return "NO_EVIDENCE"


def _safe_issue(component: str, code: str, **extra: Any) -> Dict[str, Any]:
    allowed = {key: value for key, value in extra.items() if key in {"count", "severity", "within_seconds", "field"}}
    return {"component": component, "code": code, **allowed}


def _collect_sources(trade_id: str, sources: Mapping[str, Any]) -> tuple[Dict[str, list[Mapping[str, Any]]], Dict[str, Any], Dict[str, Any], list, list]:
    correlation = new_correlation_context(trade_id)
    rows_by_source: Dict[str, list[Mapping[str, Any]]] = {}
    raw_by_source: Dict[str, Any] = {}
    status: Dict[str, Any] = {}
    warnings, errors = [], []

    for name in SOURCE_ORDER:
        source = sources.get(name)
        if source is None:
            rows_by_source[name] = []
            status[name] = {"status": "UNAVAILABLE", "records": 0}
            continue
        try:
            value = source(trade_id) if callable(source) else source
            candidates = _records(value)
            if name == "external_exposure":
                matched = candidates
            else:
                matched = correlate_source_records(name, candidates, correlation)
            rows_by_source[name] = matched
            raw_by_source[name] = value
            source_state = _source_status(value, matched)
            meta = _metadata(value)
            status[name] = {
                "status": source_state,
                "records": len(matched),
                **{key: meta[key] for key in ("lines_scanned", "valid_lines", "invalid_lines", "partial", "bytes_scanned", "coverage_limited") if key in meta},
            }
            if meta.get("invalid_lines", 0):
                warnings.append(_safe_issue(name, "CORRUPT_JSONL_LINES_SKIPPED", count=int(meta["invalid_lines"])))
        except Exception as exc:
            rows_by_source[name] = []
            raw_by_source[name] = None
            status[name] = {"status": "ERROR", "records": 0, "error_type": type(exc).__name__}
            errors.append(_safe_issue(name, "SOURCE_READ_ERROR"))
    return rows_by_source, raw_by_source, status, warnings, errors


def _direct_first(records: Iterable[Mapping[str, Any]], *keys: str) -> Any:
    """Read root/direct Registry metadata only; never descend into limits."""
    rows = list(records)
    for record in reversed(rows):
        metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        for container in (record, metadata):
            for key in keys:
                if container.get(key) not in (None, ""):
                    return container.get(key)
    return None


def _direct_first_by_alias(records: Iterable[Mapping[str, Any]], *keys: str) -> Any:
    """Honor canonical alias precedence across root and direct metadata."""
    rows = list(records)
    for key in keys:
        for record in reversed(rows):
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            for container in (record, metadata):
                if container.get(key) not in (None, ""):
                    return container.get(key)
    return None


def _registry_initial_quantity(rows: list[Mapping[str, Any]]) -> Any:
    return _direct_first_by_alias(rows, "initial_quantity", "initial_qty", "original_quantity", "quantity", "qty")


def _registry_remaining_quantity(rows: list[Mapping[str, Any]]) -> Any:
    remaining = _direct_first_by_alias(rows, "remaining_quantity", "remaining_qty", "quantity_open", "open_qty")
    return remaining if remaining not in (None, "") else _registry_initial_quantity(rows)


def _registry_block(rows: list[Mapping[str, Any]], status: str) -> Dict[str, Any]:
    return {
        "available": status not in {"UNAVAILABLE", "ERROR"},
        "record_found": bool(rows),
        "registry_status": _first(rows, "status"),
        "bot": _first(rows, "bot", "bot_name"),
        "setup": _first(rows, "setup", "strategy"),
        "symbol": _first(rows, "symbol"),
        "side": _first(rows, "side"),
        "mode": _first(rows, "mode", "execution_mode", "registry_mode"),
        "opened_at": _first(rows, "opened_at"),
        "closed_at": _first(rows, "closed_at"),
        "entry_price": _first(rows, "entry", "entry_price"),
        "exit_price": _first(rows, "exit_price", "close_price"),
        "initial_quantity": _registry_initial_quantity(rows),
        "remaining_quantity": _registry_remaining_quantity(rows),
        "tp50_status": _first(rows, "tp50_status", "tp50_hit"),
        "break_even_status": _first(rows, "break_even_status", "breakeven", "be_moved"),
        "trailing_status": _first(rows, "trailing_status", "trailing_active"),
        "close_status": _first(rows, "close_status"),
        "last_event": _first(rows, "last_event", "event_type", "event"),
        "last_event_at": _first(rows, "last_event_at", "last_update", "updated_at"),
        "source_authority": "CENTRAL_QUANT",
    }


def _lifecycle_block(rows: list[Mapping[str, Any]], status: str) -> Dict[str, Any]:
    events = _event_names(rows)
    state = str(_first(rows, "state", "current_state") or "UNKNOWN").upper()
    history = _first(rows, "events_applied", "history")
    disaster_stop = _lifecycle_bucket(rows, "disaster_stop")
    tp50 = _lifecycle_bucket(rows, "tp50")
    break_even = _lifecycle_bucket(rows, "break_even")
    trailing = _lifecycle_bucket(rows, "trailing")
    close = _lifecycle_bucket(rows, "close")
    outcome = _lifecycle_bucket(rows, "outcome")
    return {
        "available": status not in {"UNAVAILABLE", "ERROR"},
        "lifecycle_found": bool(rows),
        "lifecycle_id": _first(rows, "lifecycle_id"),
        "current_state": state,
        "previous_state": _first(rows, "previous_state"),
        "transition_count": len(history) if isinstance(history, list) else len(events),
        "last_transition": events[-1] if events else None,
        "last_transition_at": _first(rows, "last_transition_at", "occurred_at", "updated_at"),
        "entry_confirmed": _confirmed_lifecycle_event(rows, "ENTRY_CONFIRMED") or state in ENTRY_CONFIRMED_STATES,
        "disaster_stop_confirmed": _confirmed_lifecycle_event(rows, "DISASTER_STOP_CONFIRMED") or _bool(disaster_stop.get("confirmed")) or state in PROTECTED_STATES,
        "tp50_confirmed": _confirmed_lifecycle_event(rows, "TP50_CONFIRMED") or _bool(tp50.get("confirmed")) or state in {"TP50_CONFIRMED", "RUNNER_PROTECTED"},
        "break_even_confirmed": _confirmed_lifecycle_event(rows, "BREAK_EVEN_CONFIRMED") or _bool(break_even.get("confirmed")) or state == "BREAK_EVEN_ACTIVE",
        "trailing_confirmed": _confirmed_lifecycle_event(rows, "TRAILING_CONFIRMED") or _bool(trailing.get("confirmed")) or state == "TRAILING_ACTIVE",
        "close_confirmed": _confirmed_lifecycle_event(rows, "CLOSE_CONFIRMED") or _bool(close.get("confirmed")) or state in CLOSED_LIFECYCLE_STATES,
        "outcome_recorded": _confirmed_lifecycle_event(rows, "OUTCOME_CONFIRMED") or _bool(outcome.get("confirmed")) or state in {"OUTCOME_RECORDED", "LEARNING_ELIGIBLE"},
        "learning_eligible": _confirmed_lifecycle_event(rows, "LEARNING_ELIGIBILITY_CONFIRMED") or state == "LEARNING_ELIGIBLE",
        "blocked_events": int(_first(rows, "blocked_events") or 0),
        "divergences": copy.deepcopy(_first(rows, "divergences") or []),
        "source_authority": "CENTRAL_QUANT_LIFECYCLE",
    }


def _direct_event_name(record: Mapping[str, Any]) -> str:
    return str(record.get("event_type") or record.get("event") or record.get("action") or "").upper().strip().replace(" ", "_")


def _broker_send_confirmed(record: Mapping[str, Any]) -> bool:
    status = str(record.get("status") or "").upper().strip()
    order_id = record.get("order_id") or record.get("broker_order_id") or record.get("exchange_order_id") or record.get("id")
    return (
        _bool(record.get("sent"))
        and order_id not in (None, "")
        and ((_bool(record.get("ok")) and status == "SENT") or status == "LIVE_SENT_BUT_DISASTER_STOP_FAILED")
    )


def _broker_contracts(rows: list[Mapping[str, Any]]) -> Any:
    reduction_observed = any(
        _direct_event_name(record) in {
            "TP50_FILL_RECORDED", "TP50_CONFIRMED", "PARTIAL_CLOSE",
            "CLOSE_FILL_RECORDED", "CLOSE_PARTIAL_RECORDED", "CLOSE_CONFIRMED",
            "LIVE_TRADE_CLOSED",
        }
        for record in rows
    )
    for record in reversed(rows):
        event_name = _direct_event_name(record)
        if "DISASTER_STOP" in event_name:
            continue
        value = _direct_first([record], "contracts")
        if value not in (None, ""):
            return value
    if not reduction_observed:
        for record in reversed(rows):
            event_name = _direct_event_name(record)
            if event_name in {
                "BROKER_LIVE_SENT", "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED",
                "PLACE_MARKET_ORDER",
            } and _broker_send_confirmed(record):
                value = _direct_first([record], "contracts", "quantity", "qty", "amount")
                if value not in (None, ""):
                    return value
    for record in reversed(rows):
        event_name = _direct_event_name(record)
        position_fact = record.get("position_found") is True or str(record.get("position_status") or "").upper() in {"OPEN", "ACTIVE"}
        if position_fact and "DISASTER_STOP" not in event_name:
            value = _direct_first([record], "quantity", "qty")
            if value not in (None, ""):
                return value
    return None


def _positive_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalized_symbol(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).upper().strip().replace("-", "").replace("/", "")
    if ":" in text:
        text = text.split(":", 1)[0]
    return text or None


def _normalized_position_side(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).upper().strip()
    if text in {"BUY", "LONG"}:
        return "LONG"
    if text in {"SELL", "SHORT"}:
        return "SHORT"
    return text or None


def _normalized_stop_evidence(payload: Mapping[str, Any], source_event: str) -> Dict[str, Any]:
    return {
        "created": True,
        "confirmed": False,
        "order_id": payload.get("disaster_stop_order_id") or payload.get("broker_stop_order_id") or payload.get("order_id"),
        "client_order_id": payload.get("client_order_id") or payload.get("clientOrderId"),
        "price": payload.get("disaster_stop_price") or payload.get("stop_price") or payload.get("trigger_price") or payload.get("original_stop_price"),
        "quantity": payload.get("disaster_stop_quantity") or payload.get("protected_quantity") or payload.get("amount"),
        "status": payload.get("disaster_stop_status") or payload.get("status") or "DISASTER_STOP_CREATED",
        "symbol": payload.get("symbol") or payload.get("bingx_symbol"),
        "position_side": payload.get("position_side") or payload.get("positionSide"),
        "action_side": payload.get("side"),
        "source_event": source_event,
    }


def _qualify_stop_evidence(
    evidence: Dict[str, Any],
    expected_quantity: Any,
    expected_symbol: Any = None,
    expected_side: Any = None,
) -> Dict[str, Any]:
    price = _positive_number(evidence.get("price"))
    quantity = _positive_number(evidence.get("quantity"))
    if price is None or quantity is None:
        evidence["validation_error"] = "STOP_PRICE_OR_QUANTITY_MISSING"
        return evidence
    expected = _positive_number(expected_quantity)
    if expected is not None and abs(quantity - expected) > max(1e-8, abs(expected) * 1e-8):
        evidence["validation_error"] = "PROTECTED_QUANTITY_MISMATCH"
        return evidence
    expected_symbol_normalized = _normalized_symbol(expected_symbol)
    evidence_symbol = _normalized_symbol(evidence.get("symbol"))
    if expected_symbol_normalized and evidence_symbol and evidence_symbol != expected_symbol_normalized:
        evidence["validation_error"] = "STOP_SYMBOL_MISMATCH"
        return evidence
    expected_position_side = _normalized_position_side(expected_side)
    evidence_position_side = _normalized_position_side(evidence.get("position_side"))
    if expected_position_side and evidence_position_side and evidence_position_side != expected_position_side:
        evidence["validation_error"] = "STOP_POSITION_SIDE_MISMATCH"
        return evidence
    action_side = str(evidence.get("action_side") or "").upper().strip()
    expected_action_side = {"LONG": "SELL", "SHORT": "BUY"}.get(expected_position_side or "")
    if expected_action_side and action_side and action_side != expected_action_side:
        evidence["validation_error"] = "STOP_ACTION_SIDE_MISMATCH"
        return evidence
    evidence["price"] = price
    evidence["quantity"] = quantity
    evidence["symbol"] = evidence_symbol
    evidence["position_side"] = evidence_position_side
    evidence["action_side"] = action_side or None
    evidence["confirmed"] = True
    return evidence


def _broker_disaster_stop(
    rows: list[Mapping[str, Any]],
    expected_quantity: Any = None,
    expected_symbol: Any = None,
    expected_side: Any = None,
) -> Dict[str, Any]:
    """Normalize already-persisted physical stop evidence; never call Broker."""
    for record in reversed(rows):
        event_name = _direct_event_name(record)
        nested = record.get("disaster_stop")
        if (
            event_name == "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED"
            and _broker_send_confirmed(record)
            and isinstance(nested, Mapping)
            and not _bool(nested.get("ok"))
            and not _bool(nested.get("created"))
        ):
            return {
                "created": False,
                "confirmed": False,
                "status": nested.get("status") or "DISASTER_STOP_FAILED",
                "source_event": event_name,
                "validation_error": "DISASTER_STOP_CREATION_FAILED",
                "error": nested.get("error") or record.get("error"),
            }
        if (
            event_name == "BROKER_DISASTER_STOP_ERROR"
            and not _bool(record.get("ok"))
            and not _bool(record.get("created"))
            and str(record.get("status") or "").upper().strip() == "DISASTER_STOP_ERROR"
        ):
            return {
                "created": False,
                "confirmed": False,
                "status": "DISASTER_STOP_ERROR",
                "source_event": event_name,
                "validation_error": "DISASTER_STOP_CREATION_FAILED",
                "error": record.get("error"),
            }
        if (
            event_name == "BROKER_DISASTER_STOP_CREATED"
            and _bool(record.get("ok"))
            and _bool(record.get("created"))
            and str(record.get("status") or "").upper().strip() == "DISASTER_STOP_CREATED"
            and record.get("order_id") not in (None, "")
        ):
            return _qualify_stop_evidence(
                _normalized_stop_evidence(record, event_name),
                expected_quantity,
                expected_symbol,
                expected_side,
            )

        if (
            event_name == "BROKER_LIVE_SENT"
            and _broker_send_confirmed(record)
            and isinstance(nested, Mapping)
            and _bool(nested.get("ok"))
            and _bool(nested.get("created"))
            and nested.get("order_id") not in (None, "")
        ):
            return _qualify_stop_evidence(
                _normalized_stop_evidence(nested, "BROKER_LIVE_SENT.disaster_stop"),
                expected_quantity,
                expected_symbol,
                expected_side,
            )
    return {}


def _broker_position_side(rows: list[Mapping[str, Any]]) -> Any:
    for record in reversed(rows):
        value = _direct_first([record], "position_side", "positionSide")
        if value not in (None, ""):
            return value
    for record in reversed(rows):
        if "DISASTER_STOP" not in _direct_event_name(record):
            value = _direct_first([record], "side")
            if value not in (None, ""):
                return value
    return None


def _broker_block(rows: list[Mapping[str, Any]], source_value: Any, status: str) -> Dict[str, Any]:
    explicit_found = _first(rows, "position_found")
    raw_status = str(_first(rows, "position_status", "status") or "").upper()
    found = bool(rows) if explicit_found is None else bool(explicit_found)
    if raw_status in {"CLOSED", "FLAT", "NOT_FOUND", "NO_POSITION"}:
        found = False
    ready = source_value.get("ready") if isinstance(source_value, Mapping) else None
    return {
        "available": status not in {"UNAVAILABLE", "ERROR"},
        "ready": bool(ready) if ready is not None else status == "AVAILABLE",
        "matched_position": bool(rows),
        "position_found": found,
        "symbol": _first(rows, "symbol"),
        "side": _broker_position_side(rows),
        "contracts": _broker_contracts(rows),
        "entry_price": _first(rows, "entry_price", "entry", "average_price"),
        "mark_price": _first(rows, "mark_price", "current_price"),
        "unrealized_pnl": _first(rows, "unrealized_pnl", "unrealizedPnl"),
        "leverage": _first(rows, "leverage"),
        "broker_order_ids": sorted(set(_identity_values(rows).get(key) for key in ("broker_order_id", "exchange_order_id", "order_id") if _identity_values(rows).get(key))),
        "open_orders": copy.deepcopy(_first(rows, "open_orders") or []),
        "protective_orders": copy.deepcopy(_first(rows, "protective_orders") or []),
        "last_sync_at": _first(rows, "last_sync_at", "updated_at", "timestamp"),
        "source_authority": "CUSTODIAN",
    }


def build_live_trade_snapshot(
    trade_id: str,
    *,
    sources: Optional[Mapping[str, Any]] = None,
    now_epoch: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Constroi snapshot sem escrita, rede, broker ou autoridade operacional."""
    started = time.perf_counter()
    active_logger = logger or LOGGER
    try:
        identity = _safe_id(trade_id)
        source_map = dict(sources) if sources is not None else build_default_sources()
        rows, raw_sources, component_status, warnings, errors = _collect_sources(identity, source_map)

        validator_sources = {}
        for name in TIMELINE_COMPONENTS:
            if component_status.get(name, {}).get("status") == "ERROR":
                def failed_source(_trade_id: str, component=name):
                    raise OSError(f"{component} source unavailable")
                validator_sources[name] = failed_source
            else:
                validator_sources[name] = rows.get(name, [])
        try:
            timeline_report = validate_trade_timeline(identity, sources=validator_sources, logger=active_logger)
        except Exception as exc:
            timeline_report = {"result": "FAIL", "valid": False, "fail_open": True, "production_blocked": False, "errors": [{"error_type": type(exc).__name__}]}
            errors.append(_safe_issue("timeline_validation", "VALIDATOR_ERROR"))

        registry = _registry_block(rows["registry"], component_status["registry"]["status"])
        lifecycle = _lifecycle_block(rows["lifecycle"], component_status["lifecycle"]["status"])
        broker = _broker_block(rows["broker"], raw_sources.get("broker"), component_status["broker"]["status"])
        expected_stop_quantity = registry.get("remaining_quantity") if registry.get("remaining_quantity") not in (None, "") else broker.get("contracts")
        expected_stop_symbol = registry.get("symbol") if registry.get("symbol") not in (None, "") else broker.get("symbol")
        expected_stop_side = registry.get("side") if registry.get("side") not in (None, "") else broker.get("side")
        broker_stop = _broker_disaster_stop(
            rows["broker"],
            expected_stop_quantity,
            expected_stop_symbol,
            expected_stop_side,
        )
        identities: Dict[str, str] = {"trade_id": identity}
        for name in SOURCE_ORDER:
            if name != "external_exposure":
                for key, value in _identity_values(rows.get(name, [])).items():
                    identities.setdefault(key, value)
        matched_records = sum(len(rows.get(name, [])) for name in SOURCE_ORDER if name != "external_exposure")
        matched_by = [key for key in IDENTITY_KEYS if key in identities] if matched_records else []

        registry_status = str(registry.get("registry_status") or "UNKNOWN").upper()
        trade_status = "CLOSED" if registry_status == "CLOSED" else ("OPEN" if registry_status == "OPEN" else ("PENDING" if "PENDING" in registry_status else "UNKNOWN"))
        mode = str(registry.get("mode") or _first(rows["lifecycle"], "mode") or "UNKNOWN").upper()
        opened_epoch = _timestamp_epoch(registry.get("opened_at"))
        current_epoch = float(now_epoch if now_epoch is not None else time.time())
        age_seconds = max(0.0, current_epoch - opened_epoch) if opened_epoch is not None else None

        execution_rows = rows["execution_engine"] + rows["execution_orchestrator"] + rows["broker"]
        execution_events = _event_names(execution_rows)
        canonical_timeline_events = {item.get("event") for item in (timeline_report.get("events_found") or []) if isinstance(item, Mapping)}
        management_events = _event_names(rows["lifecycle"] + rows["history_manager"] + rows["timeline"] + rows["falcon"])
        shadow_events = _event_names(rows["shadow_runtime"])
        telegram_events = _event_names(rows["telegram"])

        protection_confirmed = lifecycle["disaster_stop_confirmed"] or _bool(_direct_first(rows["registry"], "disaster_stop_confirmed")) or bool(broker_stop.get("confirmed"))
        if broker_stop.get("validation_error"):
            # A contradictory physical Broker fact is stronger than a stale
            # local confirmation flag. Remain conservatively unprotected.
            protection_confirmed = False
        disaster_required = trade_status == "OPEN" and mode in {"LIVE", "REAL"}
        unprotected = bool(disaster_required and not protection_confirmed)
        protection_status = "PROTECTED" if protection_confirmed else ("MISSING" if unprotected else "NOT_APPLICABLE" if not disaster_required else "UNKNOWN")

        divergences = []
        pending = []
        if broker["position_found"] and not registry["record_found"]:
            divergences.append(_safe_issue("registry_broker", "BROKER_POSITION_WITHOUT_REGISTRY", severity="CRITICAL"))
        if registry["record_found"] and trade_status == "OPEN" and not broker["position_found"]:
            if age_seconds is not None and age_seconds <= GRACE_WINDOWS["broker_ack_grace_seconds"]:
                pending.append(_safe_issue("broker", "PENDING_WITHIN_GRACE_WINDOW", within_seconds=GRACE_WINDOWS["broker_ack_grace_seconds"]))
            else:
                divergences.append(_safe_issue("registry_broker", "REGISTRY_OPEN_WITHOUT_BROKER_POSITION", severity="CRITICAL"))
        lifecycle_state = str(lifecycle.get("current_state") or "UNKNOWN").upper()
        if registry["record_found"] and lifecycle["lifecycle_found"]:
            lifecycle_closed = lifecycle["close_confirmed"] or lifecycle_state in CLOSED_LIFECYCLE_STATES
            if (trade_status == "OPEN" and lifecycle_closed) or (trade_status == "CLOSED" and lifecycle_state not in CLOSED_LIFECYCLE_STATES):
                divergences.append(_safe_issue("registry_lifecycle", "LIFECYCLE_REGISTRY_STATE_CONFLICT", severity="CRITICAL"))
        if unprotected:
            divergences.append(_safe_issue("risk_protection", "LIVE_POSITION_WITHOUT_DISASTER_STOP", severity="CRITICAL"))
        if broker_stop.get("validation_error"):
            validation_code = str(broker_stop["validation_error"])
            validation_field = {
                "STOP_SYMBOL_MISMATCH": "disaster_stop_symbol",
                "STOP_POSITION_SIDE_MISMATCH": "disaster_stop_position_side",
                "STOP_ACTION_SIDE_MISMATCH": "disaster_stop_action_side",
                "DISASTER_STOP_CREATION_FAILED": "disaster_stop_status",
            }.get(validation_code, "disaster_stop_quantity")
            divergences.append(_safe_issue(
                "risk_protection",
                validation_code,
                severity="CRITICAL",
                field=validation_field,
            ))
        divergences.extend(copy.deepcopy(timeline_report.get("divergences") or []))

        expected_missing = list(timeline_report.get("events_missing") or [])
        not_due = sorted(set(expected_missing) & FINAL_EVENTS) if trade_status == "OPEN" else []
        overdue_missing = [item for item in expected_missing if item not in not_due]
        if not_due:
            warnings.append(_safe_issue("timeline_validation", "EVENTS_NOT_DUE_FOR_OPEN_TRADE", count=len(not_due)))
        warnings.extend(pending)
        warnings.extend(copy.deepcopy(timeline_report.get("warnings") or []))

        external_rows = [item for item in rows["external_exposure"] if _bool(_first([item], "external_position", "manual_position")) or str(_first([item], "ownership") or "").upper() in {"EXTERNAL", "MANUAL"}]
        symbol = registry.get("symbol")
        external_positions = [{
            "symbol": _first([item], "symbol"),
            "side": _first([item], "side"),
            "classification": "EXTERNAL",
        } for item in external_rows]

        registry_qty = registry.get("remaining_quantity")
        broker_qty = broker.get("contracts")
        if registry_qty not in (None, "") and broker_qty not in (None, ""):
            try:
                if abs(float(registry_qty) - float(broker_qty)) > max(1e-8, abs(float(registry_qty)) * 1e-8):
                    divergences.append(_safe_issue("registry_broker", "QUANTITY_CONFLICT", severity="CRITICAL", field="remaining_quantity"))
            except (TypeError, ValueError):
                pass

        relevant_component_status = {
            name: detail
            for name, detail in component_status.items()
            if name not in {"telegram", "falcon", "external_exposure"}
        }
        source_error = any(detail.get("status") == "ERROR" for detail in relevant_component_status.values())
        degraded = any(detail.get("status") in {"ERROR", "DEGRADED", "PARTIAL"} for detail in relevant_component_status.values())
        identified = bool(matched_records)
        incomplete = bool(overdue_missing or pending or (identified and not lifecycle["lifecycle_found"]))
        if not identified:
            # Cobertura parcial sem qualquer identidade correlacionada não muda
            # ausência de evidência para degradação. Um erro real de fonte torna
            # a conclusão de ausência não conclusiva, mas ainda permite snapshot.
            snapshot_status = "DEGRADED" if source_error else "NOT_FOUND"
        elif divergences:
            snapshot_status = "DIVERGENT"
        elif degraded:
            snapshot_status = "DEGRADED"
        elif incomplete:
            snapshot_status = "INCOMPLETE"
        else:
            snapshot_status = "HEALTHY"

        timeline_validation = {
            "validation_status": timeline_report.get("result", "FAIL"),
            "pass": bool(timeline_report.get("valid", False)),
            "component_status": {name: detail.get("status") for name, detail in (timeline_report.get("components") or {}).items()},
            "events_found": copy.deepcopy(timeline_report.get("events_found") or []),
            "missing_events": expected_missing,
            "not_due_events": not_due,
            "overdue_missing_events": overdue_missing,
            "duplicate_events": copy.deepcopy(timeline_report.get("events_duplicated") or []),
            "divergences": copy.deepcopy(timeline_report.get("divergences") or []),
            "latencies": copy.deepcopy(timeline_report.get("latencies") or []),
            "warnings": copy.deepcopy(timeline_report.get("warnings") or []),
            "errors": [{key: item.get(key) for key in ("component", "error_type", "code") if item.get(key)} for item in (timeline_report.get("errors") or []) if isinstance(item, Mapping)],
            "fail_open": True,
            "production_blocked": False,
        }

        result = {
            "ok": True,
            "snapshot_version": SNAPSHOT_VERSION,
            "generated_at": _now_iso(),
            "trade_id": identity,
            "snapshot_status": snapshot_status,
            "trade_status": trade_status,
            "fail_open": True,
            "production_blocked": False,
            "operational_impact": False,
            "identity": {**{key: identities.get(key) for key in ("trade_id", "registry_id", "lifecycle_id", "execution_id", "decision_id", "signal_id", "client_order_id", "broker_order_id")}, "correlation_ids": sorted(set(identities.values())), "matched_by": sorted(matched_by), "identity_confidence": "HIGH" if identified else "NONE"},
            "trade": {
                "bot": registry.get("bot"), "setup": registry.get("setup"), "symbol": symbol,
                "side": registry.get("side"), "mode": mode, "status": trade_status,
                "opened_at": registry.get("opened_at"), "closed_at": registry.get("closed_at"),
                "age_seconds": age_seconds, "entry_price": registry.get("entry_price"),
                "current_price": broker.get("mark_price") if broker.get("matched_position") else None,
                "exit_price": registry.get("exit_price"), "original_quantity": registry.get("initial_quantity"),
                "remaining_quantity": registry.get("remaining_quantity"), "leverage": _first(rows["registry"], "leverage"),
                "risk_usdt": _first(rows["registry"], "risk_usdt"), "risk_pct": _first(rows["registry"], "risk_pct"),
                "realized_pnl_usdt": _first(rows["registry"], "realized_pnl", "realized_pnl_usdt"),
                "unrealized_pnl_usdt": broker.get("unrealized_pnl") if broker.get("matched_position") else None,
                "realized_pnl_pct": _first(rows["registry"], "pnl_pct", "result_pct"),
                "realized_r": _first(rows["registry"], "pnl_r", "result_r"),
                "exit_reason": _first(rows["registry"], "exit_reason", "close_reason"),
                "field_sources": {"identity": "TRADE_REGISTRY", "statistics": "TRADE_REGISTRY", "custody": "BROKER_MATCHED_IDENTITY" if broker.get("matched_position") else "UNAVAILABLE"},
            },
            "broker": broker,
            "registry": registry,
            "lifecycle": lifecycle,
            "execution": {
                "decision": _first(execution_rows, "decision"), "route": _first(execution_rows, "route"),
                "execution_requested": "EXECUTION_REQUESTED" in canonical_timeline_events or any(name in execution_events for name in ("EXECUTION_REQUESTED", "EXECUTION_PLAN_CREATED", "ENTRY_INTENT_CREATED")),
                "order_sent": "LIVE_ORDER_SENT" in canonical_timeline_events or any(name in execution_events for name in ("LIVE_ORDER_SENT", "ENTRY_SUBMITTED", "ORDER_SENT")),
                "broker_acknowledged": "BROKER_ACK" in canonical_timeline_events or any(name in execution_events for name in ("BROKER_ACK", "ENTRY_FILL_RECORDED", "ORDER_ACCEPTED")),
                "execution_status": _first(execution_rows, "execution_status", "status"),
                "last_execution_event": execution_events[-1] if execution_events else None,
                "last_execution_at": _first(execution_rows, "occurred_at", "timestamp", "updated_at"),
                "fail_safe_action": _first(execution_rows, "fail_safe_action"),
                "execution_errors": [],
                "engine_status": component_status["execution_engine"]["status"],
                "orchestrator_status": component_status["execution_orchestrator"]["status"],
            },
            "risk_protection": {
                "disaster_stop_required": disaster_required, "disaster_stop_created": _bool(_first(rows["lifecycle"], "disaster_stop_created")) or bool(broker_stop.get("created")) or protection_confirmed,
                "disaster_stop_confirmed": protection_confirmed, "disaster_stop_order_id": broker_stop.get("order_id") or _first(rows["lifecycle"], "disaster_stop_order_id"),
                "disaster_stop_price": broker_stop.get("price") or _first(rows["lifecycle"], "disaster_stop_price", "trigger_price"),
                "disaster_stop_quantity": broker_stop.get("quantity") or _first(rows["lifecycle"], "disaster_stop_quantity", "protected_quantity"),
                "disaster_stop_status": broker_stop.get("status") or _first(rows["lifecycle"], "disaster_stop_status"),
                "fail_safe_action": _first(execution_rows, "fail_safe_action"), "unprotected_position": unprotected,
                "protection_status": protection_status,
            },
            "management": {
                "tp50_expected": _first(rows["registry"], "tp50") is not None, "tp50_triggered": any("TP50" in name for name in management_events),
                "tp50_confirmed": lifecycle["tp50_confirmed"], "tp50_quantity": _first(rows["lifecycle"], "tp50_quantity"), "tp50_price": _first(rows["lifecycle"], "tp50_price"),
                "break_even_expected": lifecycle["tp50_confirmed"], "break_even_applied": lifecycle["break_even_confirmed"], "break_even_stop_price": _first(rows["lifecycle"] + rows["falcon"], "break_even_stop_price", "new_stop"),
                "trailing_expected": lifecycle["break_even_confirmed"], "trailing_active": lifecycle["trailing_confirmed"], "trailing_update_count": sum(1 for name in management_events if "TRAILING" in name),
                "trailing_last_price": _first(rows["lifecycle"] + rows["falcon"], "trailing_last_price", "new_sl"), "trailing_last_at": _first(rows["lifecycle"] + rows["falcon"], "trailing_last_at"),
                "partial_close_count": sum(1 for name in management_events if "PARTIAL" in name), "remaining_quantity": registry.get("remaining_quantity"),
                "final_close_confirmed": lifecycle["close_confirmed"], "last_management_action": management_events[-1] if management_events else None,
                "last_management_at": _first(rows["lifecycle"] + rows["falcon"], "occurred_at", "updated_at"), "management_errors": [],
            },
            "shadow": {
                "available": component_status["shadow_runtime"]["status"] not in {"UNAVAILABLE", "ERROR"}, "observed": bool(rows["shadow_runtime"]),
                "matched": "SHADOW_VALIDATED" in canonical_timeline_events,
                "shadow_status": _first(rows["shadow_runtime"], "status", "comparison"), "last_shadow_event": shadow_events[-1] if shadow_events else None,
                "last_shadow_at": _first(rows["shadow_runtime"], "timestamp", "occurred_at"), "divergence_count": len(timeline_report.get("divergences") or []),
                "divergences": copy.deepcopy(timeline_report.get("divergences") or []), "operational_authority": False,
            },
            "telegram": {
                "live_order_notification": any("ORDER" in name and "LIVE" in name for name in telegram_events), "disaster_stop_notification": any("DISASTER_STOP" in name for name in telegram_events),
                "tp50_notification": any("TP50" in name for name in telegram_events), "break_even_notification": any("BREAK_EVEN" in name or "BREAKEVEN" in name for name in telegram_events),
                "trailing_notification_count": sum(1 for name in telegram_events if "TRAILING" in name), "close_notification": any("CLOSE" in name for name in telegram_events),
                "notification_errors": [], "last_notification_at": _first(rows["telegram"], "timestamp", "occurred_at"), "source_authority": "OBSERVATIONAL",
            },
            "timeline_validation": timeline_validation,
            "external_exposure": {"detected": bool(external_positions), "count": len(external_positions), "positions": external_positions, "overlaps_symbol": any(item.get("symbol") == symbol for item in external_positions) if symbol else False, "managed_by_central": False},
            "component_status": component_status,
            "divergences": divergences,
            "warnings": warnings,
            "errors": errors,
            "grace_windows_seconds": dict(GRACE_WINDOWS),
            "coverage": {name: {key: detail.get(key) for key in ("partial", "bytes_scanned", "coverage_limited") if key in detail} for name, detail in component_status.items()},
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        json.dumps(result, ensure_ascii=False, default=str)
        return result
    except Exception as exc:
        try:
            active_logger.exception("live trade snapshot failed: %s", type(exc).__name__)
        except Exception:
            pass
        raw_identity = str(trade_id or "")
        public_identity = "" if (
            any(char in raw_identity for char in ("/", "\\", "\x00"))
            or any(ord(char) < 32 or ord(char) == 127 for char in raw_identity)
        ) else raw_identity[:MAX_TRADE_ID_LENGTH]
        return {
            "ok": False, "snapshot_version": SNAPSHOT_VERSION, "generated_at": _now_iso(),
            "trade_id": public_identity, "snapshot_status": "ERROR",
            "trade_status": "UNKNOWN", "fail_open": True, "production_blocked": False,
            "operational_impact": False, "identity": {}, "trade": {}, "broker": {},
            "registry": {}, "lifecycle": {}, "execution": {}, "risk_protection": {},
            "management": {}, "shadow": {}, "telegram": {}, "timeline_validation": {},
            "external_exposure": {}, "component_status": {}, "divergences": [],
            "warnings": [], "errors": [{"component": "snapshot", "code": "SNAPSHOT_INTERNAL_ERROR", "error_type": type(exc).__name__}],
        }


__all__ = ["GRACE_WINDOWS", "SNAPSHOT_VERSION", "build_live_trade_snapshot"]
