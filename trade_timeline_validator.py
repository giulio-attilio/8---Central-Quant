"""Trade Timeline Validator V1.

Camada estritamente observacional para reconstruir e validar a linha temporal de
um trade. O modulo nao importa componentes operacionais: as fontes padrao sao
arquivos locais lidos sob demanda e fontes alternativas podem ser injetadas.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional


VERSION = "2026-07-13-TRADE-TIMELINE-VALIDATOR-V1"
LOGGER = logging.getLogger(__name__)
JSONL_MAX_BYTES = 64 * 1024 * 1024
JSONL_MAX_VALID_LINES = 100_000
CORRELATION_PRE_OPEN_SECONDS = 15 * 60
CORRELATION_POST_CLOSE_SECONDS = 24 * 60 * 60
ENTRY_REFERENCE_TOLERANCE_RATIO = 0.001

COMPONENTS = (
    "registry",
    "lifecycle",
    "history_manager",
    "execution_engine",
    "execution_orchestrator",
    "broker",
    "shadow_runtime",
    "timeline",
    "telegram",
)

REQUIRED_EVENTS = (
    "SIGNAL_RECEIVED",
    "RISK_APPROVED",
    "EXECUTION_REQUESTED",
    "LIVE_ORDER_SENT",
    "BROKER_ACK",
    "POSITION_OPEN",
    "LIVE_TRADE_CLOSED",
    "REGISTRY_CLOSE",
    "LIFECYCLE_FINISHED",
    "SHADOW_VALIDATED",
)

EVENT_ORDER = (
    "SIGNAL_RECEIVED",
    "RISK_APPROVED",
    "EXECUTION_REQUESTED",
    "LIVE_ORDER_SENT",
    "BROKER_ACK",
    "POSITION_OPEN",
    "TP50",
    "BREAK_EVEN",
    "TRAILING_UPDATED",
    "PARTIAL_CLOSE",
    "LIVE_TRADE_CLOSED",
    "REGISTRY_CLOSE",
    "LIFECYCLE_FINISHED",
    "SHADOW_VALIDATED",
)

REPEATABLE_EVENTS = {"TRAILING_UPDATED", "PARTIAL_CLOSE"}
OBSERVATIONAL_META_EVENTS = {"SHADOW_VALIDATED"}
LIFECYCLE_TERMINAL_STATES = {"OUTCOME_RECORDED", "LEARNING_ELIGIBLE"}

EVENT_ALIASES = {
    "SIGNAL": "SIGNAL_RECEIVED",
    "SIGNAL_CREATED": "SIGNAL_RECEIVED",
    "SIGNAL_RECEIVED": "SIGNAL_RECEIVED",
    "RISK_ALLOW": "RISK_APPROVED",
    "RISK_APPROVED": "RISK_APPROVED",
    "RISK_APPROVED_RECORDED": "RISK_APPROVED",
    "DECISION_ALLOWED": "RISK_APPROVED",
    "DECISION_ALLOWED_RECORDED": "RISK_APPROVED",
    "EXECUTION_PLAN_CREATED": "EXECUTION_REQUESTED",
    "EXECUTION_REQUESTED": "EXECUTION_REQUESTED",
    "ENTRY_INTENT_CREATED": "EXECUTION_REQUESTED",
    "ENTRY_SUBMITTED": "LIVE_ORDER_SENT",
    "LIVE_ORDER_SENT": "LIVE_ORDER_SENT",
    "ORDER_SENT": "LIVE_ORDER_SENT",
    "ORDER_SUBMITTED": "LIVE_ORDER_SENT",
    "BROKER_ACK": "BROKER_ACK",
    "ORDER_ACK": "BROKER_ACK",
    "ORDER_ACCEPTED": "BROKER_ACK",
    "ENTRY_FILL_RECORDED": "BROKER_ACK",
    "POSITION_OPEN": "POSITION_OPEN",
    "POSITION_OPENED": "POSITION_OPEN",
    "TRADE_OPENED": "POSITION_OPEN",
    "ENTRY_CONFIRMED": "POSITION_OPEN",
    "TP50": "TP50",
    "TP50_HIT": "TP50",
    "TP50_CONFIRMED": "TP50",
    "TP50_FILL_RECORDED": "TP50",
    "BE": "BREAK_EVEN",
    "BREAKEVEN": "BREAK_EVEN",
    "BREAK_EVEN": "BREAK_EVEN",
    "BREAK_EVEN_CONFIRMED": "BREAK_EVEN",
    "TRAIL": "TRAILING_UPDATED",
    "TRAILING": "TRAILING_UPDATED",
    "TRAILING_CONFIRMED": "TRAILING_UPDATED",
    "TRAILING_UPDATED": "TRAILING_UPDATED",
    "PARTIAL_CLOSE": "PARTIAL_CLOSE",
    "CLOSE_PARTIAL_RECORDED": "PARTIAL_CLOSE",
    "LIVE_TRADE_CLOSED": "LIVE_TRADE_CLOSED",
    "TRADE_CLOSED": "LIVE_TRADE_CLOSED",
    "CLOSE_CONFIRMED": "LIVE_TRADE_CLOSED",
    "REGISTRY_CLOSE": "REGISTRY_CLOSE",
    "TRADE_CLOSED_REGISTRY": "REGISTRY_CLOSE",
    "LIFECYCLE_FINISHED": "LIFECYCLE_FINISHED",
    "OUTCOME_CONFIRMED": "LIFECYCLE_FINISHED",
    "OUTCOME_RECORDED": "LIFECYCLE_FINISHED",
    "LEARNING_ELIGIBILITY_CONFIRMED": "LIFECYCLE_FINISHED",
    "SHADOW_VALIDATED": "SHADOW_VALIDATED",
}

IDENTITY_KEYS = {
    "trade_id",
    "trade_uuid",
    "lifecycle_id",
    "registry_id",
    "execution_id",
    "decision_id",
    "signal_id",
    "client_order_id",
    "clientorderid",
    "exchange_order_id",
    "broker_order_id",
    "broker_stop_order_id",
    "disaster_stop_order_id",
    "order_id",
    "fill_id",
    "fill_ids",
}

IDENTITY_KEY_ALIASES = {
    "clientorderid": "client_order_id",
}

IDENTITY_GROUPS = {
    "trade_id": "trade",
    "trade_uuid": "trade_uuid",
    "registry_id": "registry",
    "lifecycle_id": "lifecycle",
    "execution_id": "execution",
    "decision_id": "decision",
    "signal_id": "signal",
    "client_order_id": "client_order",
    "exchange_order_id": "order",
    "broker_order_id": "order",
    "broker_stop_order_id": "order",
    "disaster_stop_order_id": "order",
    "order_id": "order",
    "fill_id": "fill",
    "fill_ids": "fill",
}

TIMESTAMP_KEYS = (
    "occurred_at",
    "event_ts",
    "timestamp",
    "ts",
    "created_at",
    "generated_at",
    "received_at",
    "updated_at",
    "last_update",
    "opened_at",
    "closed_at",
    "epoch",
)


def _data_dir(environ: Optional[Mapping[str, str]] = None) -> Path:
    env = environ or os.environ
    configured = env.get("CENTRAL_DATA_DIR") or env.get("DATA_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parent / "data"


def _shadow_data_dir(environ: Optional[Mapping[str, str]] = None) -> Path:
    env = environ or os.environ
    configured = env.get("TRADE_LIFECYCLE_SHADOW_DATA_DIR")
    return Path(configured) if configured else _data_dir(env)


def default_source_paths(environ: Optional[Mapping[str, str]] = None) -> Dict[str, tuple[Path, ...]]:
    root = _data_dir(environ)
    shadow_root = _shadow_data_dir(environ)
    return {
        "registry": (Path((environ or os.environ).get("TRADE_REGISTRY_FILE", root / "trade_registry.json")),),
        "lifecycle": (shadow_root / "trade_lifecycle_shadow_snapshot.json", shadow_root / "trade_lifecycle_shadow_events.jsonl"),
        "history_manager": (root / "history_events.jsonl",),
        "execution_engine": (root / "execution_engine_log.jsonl", root / "execution_audit_log.jsonl"),
        "execution_orchestrator": (root / "execution_orchestrator_log.jsonl",),
        "broker": (root / "broker_executions_log.jsonl", root / "broker_execution_audit_log.jsonl"),
        "shadow_runtime": (shadow_root / "trade_lifecycle_shadow_runtime_events.jsonl", shadow_root / "trade_lifecycle_shadow_runtime_divergences.jsonl"),
        "timeline": (root / "timeline.jsonl",),
        "telegram": (root / "real_execution_telegram_notifier_v1_events.jsonl", root / "real_execution_telegram_notifier_v1_latest.json"),
    }


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _structured_log(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    payload = {"event": event, "module": "trade_timeline_validator", "version": VERSION, **fields}
    getattr(logger, level, logger.info)(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _walk_dicts(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from _walk_dicts(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_dicts(child)


def _identity_key(value: Any) -> str:
    key = str(value or "").lower().strip()
    return IDENTITY_KEY_ALIASES.get(key, key)


def _identity_pairs(record: Mapping[str, Any]) -> Dict[str, set[str]]:
    """Collect typed IDs without treating arbitrary values as ownership."""
    found: Dict[str, set[str]] = {}
    for item in _walk_dicts(record):
        for raw_key, raw_value in item.items():
            key = _identity_key(raw_key)
            if key not in IDENTITY_KEYS:
                continue
            values = raw_value if isinstance(raw_value, (list, tuple, set)) else (raw_value,)
            for value in values:
                if value in (None, "") or isinstance(value, Mapping):
                    continue
                text = str(value).strip()
                if text:
                    found.setdefault(key, set()).add(text)
    return found


def _identity_values(record: Mapping[str, Any]) -> set[str]:
    return {value for values in _identity_pairs(record).values() for value in values}


def _normalize_symbol(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).upper().strip().replace("-", "").replace("/", "")
    if ":" in text:
        text = text.split(":", 1)[0]
    return text or None


def _normalize_side(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).upper().strip()
    if text in {"BUY", "LONG"}:
        return "LONG"
    if text in {"SELL", "SHORT"}:
        return "SHORT"
    return text or None


def _direct_value(record: Mapping[str, Any], *keys: str) -> Any:
    containers = [record]
    for name in ("metadata", "payload", "evidence", "trade", "snapshot", "result"):
        value = record.get(name)
        if isinstance(value, Mapping):
            containers.append(value)
    for container in containers:
        for key in keys:
            if container.get(key) not in (None, ""):
                return container.get(key)
    return None


def _record_event_name(record: Mapping[str, Any]) -> str:
    value = _direct_value(record, "event_type", "event", "action", "type")
    return str(value or "").upper().strip().replace(" ", "_")


def _record_profile(record: Mapping[str, Any], component: str) -> Dict[str, Optional[str]]:
    event_name = _record_event_name(record)
    side_value = _direct_value(record, "position_side", "positionSide")
    if side_value in (None, "") and not (component == "broker" and "DISASTER_STOP" in event_name):
        side_value = _direct_value(record, "side", "direction")
    return {
        "bot": str(_direct_value(record, "bot", "bot_name") or "").upper().strip() or None,
        "setup": str(_direct_value(record, "setup", "strategy") or "").upper().strip() or None,
        "symbol": _normalize_symbol(_direct_value(record, "symbol", "bingx_symbol")),
        "side": _normalize_side(side_value),
    }


def _is_derived_stop_client_id(value: str) -> bool:
    return str(value or "").upper().endswith("-DS")


def _derived_stop_client_id(parent: str) -> str:
    return (str(parent or "")[:24] + "-DS")[:32]


def _strict_derived_stop_relation(
    record: Mapping[str, Any],
    component: str,
    grouped: Mapping[str, set[str]],
    context: "CorrelationContext",
) -> bool:
    """Accept ``-DS`` only as a strict child of a proven entry client ID.

    The derived value is supporting ownership evidence exclusively for a
    factual Broker disaster-stop creation. It never promotes a generic/truncated
    suffix into an independent trade identity.
    """
    event_name = _record_event_name(record)
    if component != "broker" or event_name not in {"BROKER_DISASTER_STOP_CREATED", "BROKER_DISASTER_STOP_ERROR"}:
        return False
    status = str(_direct_value(record, "status") or "").upper().strip()
    created_fact = (
        event_name == "BROKER_DISASTER_STOP_CREATED"
        and _true(_direct_value(record, "ok"))
        and _true(_direct_value(record, "created"))
        and status == "DISASTER_STOP_CREATED"
        and _direct_value(record, "order_id", "broker_stop_order_id", "disaster_stop_order_id") not in (None, "")
    )
    failed_fact = (
        event_name == "BROKER_DISASTER_STOP_ERROR"
        and not _true(_direct_value(record, "ok"))
        and not _true(_direct_value(record, "created"))
        and status == "DISASTER_STOP_ERROR"
    )
    if not (created_fact or failed_fact):
        return False
    supplied = {value for value in grouped.get("client_order", set()) if _is_derived_stop_client_id(value)}
    parents = {value for value in context.trusted.get("client_order", set()) if not _is_derived_stop_client_id(value)}
    expected = {_derived_stop_client_id(parent) for parent in parents}
    return bool(supplied & expected)


@dataclass
class CorrelationContext:
    """Typed, rejection-first correlation state shared by read-only sources."""

    trade_id: str
    trusted: Dict[str, set[str]] = field(default_factory=dict)
    trusted_typed: Dict[str, set[str]] = field(default_factory=dict)
    profile: Dict[str, Optional[str]] = field(default_factory=lambda: {"bot": None, "setup": None, "symbol": None, "side": None})
    opened_epoch: Optional[float] = None
    closed_epoch: Optional[float] = None

    def __post_init__(self) -> None:
        self.trusted.setdefault("trade", set()).add(self.trade_id)
        self.trusted_typed.setdefault("trade_id", set()).add(self.trade_id)


def new_correlation_context(trade_id: str) -> CorrelationContext:
    return CorrelationContext(str(trade_id or "").strip())


def _grouped_identities(record: Mapping[str, Any]) -> Dict[str, set[str]]:
    grouped: Dict[str, set[str]] = {}
    for key, values in _identity_pairs(record).items():
        group = IDENTITY_GROUPS.get(key)
        if group:
            grouped.setdefault(group, set()).update(values)
    return grouped


def _profile_conflicts(record: Mapping[str, Any], component: str, context: CorrelationContext) -> bool:
    candidate = _record_profile(record, component)
    return any(context.profile.get(key) and value and context.profile[key] != value for key, value in candidate.items())


def _time_conflicts(record: Mapping[str, Any], context: CorrelationContext) -> bool:
    epoch, _ = _first_timestamp(record)
    if epoch is None:
        return False
    if context.opened_epoch is not None and epoch < context.opened_epoch - CORRELATION_PRE_OPEN_SECONDS:
        return True
    if (
        context.closed_epoch is not None
        and _record_event_name(record) not in OBSERVATIONAL_META_EVENTS
        and epoch > context.closed_epoch + CORRELATION_POST_CLOSE_SECONDS
    ):
        return True
    return False


def _has_scoped_identity_conflict(record: Mapping[str, Any], context: CorrelationContext) -> bool:
    # Orders, client IDs and fills repeat within one lifecycle. Canonical trade
    # aliases and instance IDs do not and must agree by their own typed field.
    pairs = _identity_pairs(record)
    for key in ("trade_uuid", "registry_id", "lifecycle_id", "execution_id", "decision_id", "signal_id"):
        known = context.trusted_typed.get(key, set())
        supplied = pairs.get(key, set())
        if known and supplied:
            if not (known & supplied):
                return True
    return False


def _unrelated_client_order(grouped: Mapping[str, set[str]], context: CorrelationContext) -> bool:
    """Reject another execution's client ID under a reused logical trade ID.

    A truncated ``-DS`` identifier is supporting context only. It is excluded
    here and can never establish ownership without another trusted identifier.
    """
    supplied = {value for value in grouped.get("client_order", set()) if not _is_derived_stop_client_id(value)}
    known = {value for value in context.trusted.get("client_order", set()) if not _is_derived_stop_client_id(value)}
    if not supplied or not known or supplied & known:
        return False
    other_instance_match = any(
        context.trusted.get(group, set()) & grouped.get(group, set())
        for group in ("lifecycle", "execution", "decision", "signal", "order")
    )
    return not other_instance_match


def _record_matches_context(record: Mapping[str, Any], component: str, context: CorrelationContext) -> bool:
    grouped = _grouped_identities(record)
    explicit_trade_ids = _identity_pairs(record).get("trade_id", set())
    if explicit_trade_ids and explicit_trade_ids != {context.trade_id}:
        return False
    if _profile_conflicts(record, component, context) or _time_conflicts(record, context):
        return False

    exact_trade = context.trade_id in explicit_trade_ids
    strong_match = False
    for group, supplied in grouped.items():
        known = context.trusted.get(group, set())
        if group == "client_order":
            supplied = {value for value in supplied if not _is_derived_stop_client_id(value)}
        if known & supplied:
            strong_match = True
            break
    derived_stop_match = _strict_derived_stop_relation(record, component, grouped, context)
    if not (exact_trade or strong_match or derived_stop_match):
        return False
    if _has_scoped_identity_conflict(record, context):
        return False
    if exact_trade and _unrelated_client_order(grouped, context):
        return False
    return True


def _promote_record(record: Mapping[str, Any], component: str, context: CorrelationContext) -> None:
    pairs = _identity_pairs(record)
    grouped = _grouped_identities(record)
    for key, values in pairs.items():
        context.trusted_typed.setdefault(key, set()).update(values)
    for group, values in grouped.items():
        safe_values = values
        if group == "client_order":
            safe_values = {value for value in values if not _is_derived_stop_client_id(value)}
        context.trusted.setdefault(group, set()).update(safe_values)
    if component == "registry":
        profile = _record_profile(record, component)
        for key, value in profile.items():
            if value:
                context.profile[key] = value
        opened_value = _direct_value(record, "opened_at")
        closed_value = _direct_value(record, "closed_at")
        opened, _ = _parse_timestamp(opened_value) if opened_value not in (None, "") else (None, None)
        closed, _ = _parse_timestamp(closed_value) if closed_value not in (None, "") else (None, None)
        if opened is not None:
            context.opened_epoch = opened
        if closed is not None:
            context.closed_epoch = closed


def _registry_candidates(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    opened = data.get("open_trades")
    if isinstance(opened, Mapping):
        candidates.extend(item for item in opened.values() if isinstance(item, Mapping))
    closed = data.get("closed_trades")
    if isinstance(closed, list):
        candidates.extend(item for item in closed if isinstance(item, Mapping))
    if isinstance(data.get("trade"), Mapping):
        candidates.append(data["trade"])
    return candidates or [data]


def _component_candidates(component: str, record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if component == "registry":
        return _registry_candidates(record)
    if component == "lifecycle" and isinstance(record.get("lifecycles"), Mapping):
        return [item for item in record["lifecycles"].values() if isinstance(item, Mapping)]
    return [record]


def _registry_rank(record: Mapping[str, Any]) -> tuple[int, float]:
    status = str(_direct_value(record, "status") or "").upper()
    epoch = None
    for key in ("opened_at", "updated_at", "closed_at", "created_at"):
        value = _direct_value(record, key)
        if value not in (None, ""):
            epoch, _ = _parse_timestamp(value)
        if epoch is not None:
            break
    return (1 if status == "OPEN" else 0, epoch or 0.0)


def correlate_source_records(
    component: str,
    records: Iterable[Mapping[str, Any]],
    context: CorrelationContext,
) -> list[Mapping[str, Any]]:
    """Return only records supported by typed IDs and consistency checks."""
    candidates = [candidate for row in records for candidate in _component_candidates(component, row)]
    if component == "registry":
        exact = [row for row in candidates if context.trade_id in _identity_pairs(row).get("trade_id", set())]
        if not exact:
            return []
        selected = max(exact, key=_registry_rank)
        if _profile_conflicts(selected, component, context):
            return []
        _promote_record(selected, component, context)
        return [selected]

    matched: list[Mapping[str, Any]] = []
    for record in candidates:
        if not _record_matches_context(record, component, context):
            continue
        matched.append(record)
        _promote_record(record, component, context)
    return matched


def _new_reader_metadata() -> Dict[str, Any]:
    return {
        "files_considered": 0,
        "files_read": 0,
        "lines_scanned": 0,
        "valid_lines": 0,
        "invalid_lines": 0,
        "partial": False,
        "bytes_scanned": 0,
        "coverage_limited": False,
    }


def _merge_reader_metadata(target: Dict[str, Any], source: Mapping[str, Any]) -> None:
    for key in ("files_considered", "files_read", "lines_scanned", "valid_lines", "invalid_lines", "bytes_scanned"):
        target[key] = int(target.get(key, 0) or 0) + int(source.get(key, 0) or 0)
    target["partial"] = bool(target.get("partial") or source.get("partial"))
    target["coverage_limited"] = bool(target.get("coverage_limited") or source.get("coverage_limited"))


def _read_path(path: Path, metadata: Optional[Dict[str, Any]] = None) -> Iterable[Mapping[str, Any]]:
    stats = metadata if metadata is not None else _new_reader_metadata()
    stats["files_considered"] = int(stats.get("files_considered", 0) or 0) + 1
    if not path.exists() or not path.is_file():
        return
    if path.suffix.lower() == ".jsonl":
        with path.open("rb") as handle:
            stats["files_read"] = int(stats.get("files_read", 0) or 0) + 1
            for raw_line in handle:
                if int(stats.get("bytes_scanned", 0) or 0) + len(raw_line) > JSONL_MAX_BYTES:
                    stats["partial"] = True
                    stats["coverage_limited"] = True
                    break
                stats["bytes_scanned"] = int(stats.get("bytes_scanned", 0) or 0) + len(raw_line)
                stats["lines_scanned"] = int(stats.get("lines_scanned", 0) or 0) + 1
                if not raw_line.strip():
                    continue
                try:
                    item = json.loads(raw_line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    stats["invalid_lines"] = int(stats.get("invalid_lines", 0) or 0) + 1
                    continue
                stats["valid_lines"] = int(stats.get("valid_lines", 0) or 0) + 1
                if isinstance(item, Mapping):
                    yield item
                if int(stats.get("valid_lines", 0) or 0) >= JSONL_MAX_VALID_LINES:
                    stats["partial"] = True
                    stats["coverage_limited"] = True
                    break
        return
    stats["files_read"] = int(stats.get("files_read", 0) or 0) + 1
    stats["bytes_scanned"] = path.stat().st_size
    data = json.loads(path.read_text(encoding="utf-8"))
    stats["valid_lines"] = 1
    if isinstance(data, Mapping):
        yield data
    elif isinstance(data, list):
        yield from (item for item in data if isinstance(item, Mapping))


def _default_reader(component: str, paths: tuple[Path, ...], context: Optional[CorrelationContext] = None) -> Callable[[str], Dict[str, Any]]:
    def read(trade_id: str) -> Dict[str, Any]:
        active_context = context if context is not None else new_correlation_context(trade_id)
        candidates: list[Mapping[str, Any]] = []
        reader_metadata = _new_reader_metadata()
        for path in paths:
            path_metadata = _new_reader_metadata()
            for row in _read_path(path, path_metadata):
                candidates.append(row)
            _merge_reader_metadata(reader_metadata, path_metadata)
        matched = correlate_source_records(component, candidates, active_context)
        return {"records": matched, "_reader_metadata": reader_metadata}

    return read


def build_default_sources(environ: Optional[Mapping[str, str]] = None) -> Dict[str, Callable[[str], Dict[str, Any]]]:
    """Constroi leitores locais. Nao le arquivos ate a validacao ser solicitada."""
    context = new_correlation_context("")

    def reader_for(name: str, paths: tuple[Path, ...]) -> Callable[[str], Dict[str, Any]]:
        def read(trade_id: str) -> Dict[str, Any]:
            if context.trade_id != str(trade_id or "").strip():
                fresh = new_correlation_context(trade_id)
                context.trade_id = fresh.trade_id
                context.trusted = fresh.trusted
                context.trusted_typed = fresh.trusted_typed
                context.profile = fresh.profile
                context.opened_epoch = None
                context.closed_epoch = None
            return _default_reader(name, paths, context)(trade_id)

        return read

    return {name: reader_for(name, paths) for name, paths in default_source_paths(environ).items()}


def _coerce_records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("records", "items", "events", "lifecycles"):
            if isinstance(value.get(key), list):
                head = {k: v for k, v in value.items() if k not in {key, "_reader_metadata"}}
                rows = [item for item in value[key] if isinstance(item, Mapping)]
                return ([head] if head else []) + rows
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _reader_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("_reader_metadata"), Mapping):
        return {}
    metadata = value["_reader_metadata"]
    return {
        "lines_scanned": int(metadata.get("lines_scanned", 0) or 0),
        "valid_lines": int(metadata.get("valid_lines", 0) or 0),
        "invalid_lines": int(metadata.get("invalid_lines", 0) or 0),
        "partial": bool(metadata.get("partial", False)),
        "bytes_scanned": int(metadata.get("bytes_scanned", 0) or 0),
        "coverage_limited": bool(metadata.get("coverage_limited", False)),
        "files_read": int(metadata.get("files_read", 0) or 0),
    }


def _parse_timestamp(value: Any) -> tuple[Optional[float], Optional[str]]:
    if value in (None, ""):
        return None, None
    if isinstance(value, (int, float)):
        epoch = float(value)
        if epoch > 10_000_000_000:
            epoch /= 1000.0
        return epoch, datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    text = str(value).strip()
    try:
        numeric = float(text)
        return _parse_timestamp(numeric)
    except ValueError:
        pass
    normalized = text.replace("Z", "+00:00")
    for parser in (
        lambda: datetime.fromisoformat(normalized),
        lambda: datetime.strptime(text, "%d/%m/%Y %H:%M"),
        lambda: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            dt = parser()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp(), dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None, text


def _first_timestamp(record: Mapping[str, Any], preferred: Optional[str] = None) -> tuple[Optional[float], Optional[str]]:
    keys = ((preferred,) if preferred else ()) + TIMESTAMP_KEYS
    for item in _walk_dicts(record):
        for key in keys:
            if key and item.get(key) not in (None, ""):
                return _parse_timestamp(item[key])
    return None, None


def _raw_event(record: Mapping[str, Any]) -> str:
    direct = _record_event_name(record)
    if direct:
        return direct
    for item in _walk_dicts(record):
        for key in ("event_type", "event", "action", "type"):
            if item.get(key) not in (None, ""):
                return str(item[key]).upper().strip().replace(" ", "_")
    return ""


def _true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").lower().strip() in {"1", "true", "yes", "sim", "on"}


def _confirmed_broker_send(record: Mapping[str, Any]) -> bool:
    status = str(_direct_value(record, "status") or "").upper().strip()
    order_id = _direct_value(record, "order_id", "broker_order_id", "exchange_order_id", "id")
    sent_with_stop_failure = status == "LIVE_SENT_BUT_DISASTER_STOP_FAILED"
    validated_fields = _direct_value(record, "validated_fields")
    validated = {str(item) for item in validated_fields} if isinstance(validated_fields, (list, tuple, set)) else set()
    required = {"trade_id", "bot", "setup", "symbol", "side", "mode", "status"}
    mode = str(_direct_value(record, "mode") or "").upper().strip()
    registry_status = str(_direct_value(record, "registry_status") or "").upper().strip()
    if mode in {"LIVE", "REAL"}:
        required.update({"quantity_open", "client_order_id", "exchange_order_id"})
        if registry_status == "OPEN":
            required.update({"protection", "disaster_stop_order_id"})
    return (
        _true(_direct_value(record, "sent"))
        and order_id not in (None, "")
        and ((_true(_direct_value(record, "ok")) and status == "SENT") or sent_with_stop_failure)
    )


def _confirmed_fill(record: Mapping[str, Any]) -> bool:
    return _direct_value(record, "fill_id") not in (None, "") and _direct_value(record, "quantity", "filled_quantity", "amount") not in (None, "")


def _decision_allow_live(record: Mapping[str, Any]) -> bool:
    candidates = [record]
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    for container in (record, metadata):
        decision = container.get("execution_decision")
        if isinstance(decision, Mapping):
            candidates.append(decision)
    for decision in candidates:
        mode = str(decision.get("mode") or decision.get("execution_mode") or _direct_value(record, "mode", "execution_mode", "registry_mode") or "").upper().strip()
        name = str(decision.get("decision") or "").upper().strip()
        if mode in {"LIVE", "REAL"} and name == "ALLOW" and _true(decision.get("allowed")):
            return True
    return False


def _explicit_decision_timestamp(record: Mapping[str, Any]) -> Any:
    """Return only a timestamp owned by the persisted execution decision.

    Registry ``opened_at``/``updated_at`` values describe persistence or the
    position, not necessarily when Risk approved the trade. Using them for a
    derived RISK_APPROVED event can invert the factual Broker chronology.
    """
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    for container in (record, metadata):
        decision = container.get("execution_decision")
        if not isinstance(decision, Mapping):
            continue
        for key in ("decided_at", "occurred_at", "timestamp", "created_at"):
            if decision.get(key) not in (None, ""):
                return decision[key]
    return None


def _shadow_match_evidence(record: Mapping[str, Any]) -> bool:
    status = str(_direct_value(record, "status", "comparison_status") or "").upper().strip()
    differences = _direct_value(record, "differences", "divergences")
    authority = _direct_value(record, "operational_authority")
    compared = _direct_value(record, "compared_fields")
    matching = _direct_value(record, "matching_fields")
    try:
        comparison_complete = int(compared) > 0 and int(matching) == int(compared)
    except (TypeError, ValueError):
        comparison_complete = False
    explicitly_observational = authority is False or str(authority or "").lower().strip() in {"0", "false", "no", "nao", "não"}
    validated_fields = _direct_value(record, "validated_fields")
    validated = {str(item) for item in validated_fields} if isinstance(validated_fields, (list, tuple, set)) else set()
    required = {"trade_id", "bot", "setup", "symbol", "side", "mode", "status"}
    mode = str(_direct_value(record, "mode") or "").upper().strip()
    registry_status = str(_direct_value(record, "registry_status") or "").upper().strip()
    if mode in {"LIVE", "REAL"}:
        required.update({"quantity_open", "client_order_id", "exchange_order_id"})
        if registry_status == "OPEN":
            required.update({"protection", "disaster_stop_order_id"})
        elif registry_status == "CLOSED":
            required.update({
                "lifecycle_terminal",
                "close_confirmed",
                "outcome_recorded",
                "quantity_closed",
                "closed_at",
                "close_reason",
            })
    validated_values = _direct_value(record, "validated_values")
    values = validated_values if isinstance(validated_values, Mapping) else {}
    live_values_valid = True
    if mode in {"LIVE", "REAL"}:
        base_value_fields = {"trade_id", "bot", "setup", "symbol", "side", "mode", "status"}
        base_values_present = all(values.get(field) not in (None, "") for field in base_value_fields)
        record_trade_id = _direct_value(record, "trade_id")
        record_client_order_id = _direct_value(record, "client_order_id")
        record_exchange_order_id = _direct_value(record, "exchange_order_id", "broker_order_id")
        record_stop_order_id = _direct_value(record, "disaster_stop_order_id", "broker_stop_order_id")
        normalized_value_mode = "LIVE" if str(values.get("mode") or "").upper().strip() in {"LIVE", "REAL"} else str(values.get("mode") or "").upper().strip()
        normalized_record_mode = "LIVE" if mode in {"LIVE", "REAL"} else mode
        coherent = bool(
            str(values.get("trade_id") or "") == str(record_trade_id or "")
            and normalized_value_mode == normalized_record_mode
            and str(values.get("status") or "").upper().strip() == registry_status
            and (record_client_order_id in (None, "") or str(values.get("client_order_id") or "") == str(record_client_order_id))
            and (record_exchange_order_id in (None, "") or str(values.get("exchange_order_id") or "") == str(record_exchange_order_id))
            and (record_stop_order_id in (None, "") or str(values.get("disaster_stop_order_id") or "") == str(record_stop_order_id))
        )
        for field, normalizer in (
            ("bot", lambda value: str(value or "").upper().strip()),
            ("setup", lambda value: str(value or "").upper().strip()),
            ("symbol", _normalize_symbol),
            ("side", _normalize_side),
        ):
            record_value = _direct_value(record, field)
            if record_value not in (None, "") and normalizer(values.get(field)) != normalizer(record_value):
                coherent = False
        live_values_valid = bool(
            base_values_present
            and values.get("client_order_id") not in (None, "")
            and values.get("exchange_order_id") not in (None, "")
            and coherent
        )

    open_values_valid = True
    if mode in {"LIVE", "REAL"} and registry_status == "OPEN":
        try:
            quantity_open_positive = float(values.get("quantity_open")) > 0
        except (TypeError, ValueError):
            quantity_open_positive = False
        open_values_valid = bool(
            quantity_open_positive
            and values.get("protection") is True
            and values.get("disaster_stop_order_id") not in (None, "")
        )

    closed_values_valid = True
    if mode in {"LIVE", "REAL"} and registry_status == "CLOSED":
        try:
            quantity_open_zero = abs(float(values.get("quantity_open"))) <= 1e-9
            quantity_closed_positive = float(values.get("quantity_closed")) > 0
        except (TypeError, ValueError):
            quantity_open_zero = False
            quantity_closed_positive = False
        closed_values_valid = bool(
            _true(values.get("lifecycle_terminal"))
            and _true(values.get("close_confirmed"))
            and _true(values.get("outcome_recorded"))
            and quantity_open_zero
            and quantity_closed_positive
            and values.get("closed_at") not in (None, "")
            and values.get("close_reason") not in (None, "")
        )
    return (
        _raw_event(record) == "SHADOW_VALIDATED"
        and status == "MATCH"
        and not differences
        and explicitly_observational
        and _true(_direct_value(record, "shadow_mode"))
        and str(_direct_value(record, "source_component") or "").upper().strip()
        == "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER"
        and comparison_complete
        and mode in {"PAPER", "VERIFY", "LIVE", "REAL"}
        and registry_status in {"OPEN", "CLOSED"}
        and required.issubset(validated)
        and live_values_valid
        and open_values_valid
        and closed_values_valid
    )


def _zero_quantity(value: Any) -> bool:
    try:
        return abs(float(value)) <= 1e-9
    except (TypeError, ValueError):
        return False


def _lifecycle_finished_evidence(record: Mapping[str, Any]) -> bool:
    """Accept only a factual, completed Manager lifecycle.

    A full snapshot proves completion through its terminal state, confirmed close,
    confirmed outcome identity, and reconciled zero open quantity.  The append-only
    event log can prove the same fact with the canonical applied outcome transition.
    Registry and Shadow records are deliberately excluded by the caller.
    """
    raw = _raw_event(record)
    previous_state = str(_direct_value(record, "previous_state") or "").upper().strip()
    current_state = str(_direct_value(record, "current_state", "state") or "").upper().strip()
    outcome_id = _direct_value(record, "outcome_id")
    if (
        raw == "OUTCOME_CONFIRMED"
        and _true(_direct_value(record, "applied", "event_applied"))
        and previous_state == "OUTCOME_PENDING"
        and current_state == "OUTCOME_RECORDED"
        and _zero_quantity(_direct_value(record, "quantity_after", "quantity_open"))
        and outcome_id not in (None, "")
    ):
        return True

    snapshot = record.get("snapshot") if isinstance(record.get("snapshot"), Mapping) else record
    state = str(snapshot.get("state") or snapshot.get("current_state") or "").upper().strip()
    close = snapshot.get("close") if isinstance(snapshot.get("close"), Mapping) else {}
    outcome = snapshot.get("outcome") if isinstance(snapshot.get("outcome"), Mapping) else {}
    snapshot_outcome_id = snapshot.get("outcome_id") or outcome.get("outcome_id")
    return bool(
        state in LIFECYCLE_TERMINAL_STATES
        and _true(close.get("confirmed"))
        and _true(outcome.get("confirmed"))
        and snapshot_outcome_id not in (None, "")
        and _zero_quantity(snapshot.get("quantity_open"))
    )


def _event(component: str, canonical: str, raw: str, record: Mapping[str, Any], preferred_ts: Optional[str] = None) -> Dict[str, Any]:
    epoch, timestamp = _first_timestamp(record, preferred_ts)
    ids = sorted(_identity_values(record))
    event_id = None
    for item in _walk_dicts(record):
        event_id = item.get("event_id") or item.get("uid")
        if event_id:
            break
    return {
        "event": canonical,
        "raw_event": raw,
        "component": component,
        "timestamp": timestamp,
        "epoch": epoch,
        "event_id": str(event_id) if event_id else None,
        "fact_order_id": str(_direct_value(record, "broker_order_id", "exchange_order_id", "order_id") or "") or None,
        "identifiers": ids,
    }


def _events_from_record(component: str, record: Mapping[str, Any]) -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = []
    embedded = []
    for key in ("events", "events_applied", "history"):
        value = record.get(key)
        if isinstance(value, list):
            embedded.extend(item for item in value if isinstance(item, Mapping))
    for item in embedded:
        events.extend(_events_from_record(component, item))

    # Embedded history is already expanded above. Do not reinterpret the parent
    # snapshot as its first nested event, which would duplicate that fact.
    raw = _record_event_name(record) if embedded else _raw_event(record)
    canonical = EVENT_ALIASES.get(raw)
    conditional_broker_alias = canonical == "BROKER_ACK"
    conditional_shadow_alias = canonical == "SHADOW_VALIDATED"
    conditional_lifecycle_finish = canonical == "LIFECYCLE_FINISHED"
    if canonical and not conditional_broker_alias and not conditional_shadow_alias and not conditional_lifecycle_finish:
        events.append(_event(component, canonical, raw, record))
    elif canonical == "BROKER_ACK" and (_confirmed_broker_send(record) or (raw == "ENTRY_FILL_RECORDED" and _confirmed_fill(record))):
        events.append(_event(component, canonical, raw, record))
    elif canonical == "SHADOW_VALIDATED" and component in {"shadow_runtime", "timeline"} and _shadow_match_evidence(record):
        events.append(_event(component, canonical, raw, record))
    elif canonical == "LIFECYCLE_FINISHED" and component == "lifecycle" and _lifecycle_finished_evidence(record):
        events.append(_event(component, canonical, raw, record))

    if component in {"registry", "history_manager", "execution_engine", "execution_orchestrator", "timeline"} and _decision_allow_live(record) and not any(item["event"] == "RISK_APPROVED" for item in events):
        risk_event = _event(component, "RISK_APPROVED", "DECISION_ALLOW_LIVE", record)
        decision_timestamp = _explicit_decision_timestamp(record)
        risk_event["epoch"], risk_event["timestamp"] = (
            _parse_timestamp(decision_timestamp) if decision_timestamp not in (None, "") else (None, None)
        )
        events.append(risk_event)

    if raw == "PLACE_MARKET_ORDER" and _confirmed_broker_send(record):
        # A factual SENT call proves the request and, when its parallel
        # BROKER_LIVE_SENT audit row is absent, the send and broker ACK too.
        events.append(_event(component, "EXECUTION_REQUESTED", raw, record))
        events.append(_event(component, "LIVE_ORDER_SENT", raw, record))
        events.append(_event(component, "BROKER_ACK", raw, record))
    if raw in {"BROKER_LIVE_SENT", "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED"} and _confirmed_broker_send(record):
        events.append(_event(component, "LIVE_ORDER_SENT", raw, record))
        events.append(_event(component, "BROKER_ACK", raw, record))

    if component == "registry":
        if record.get("opened_at") or str(record.get("status", "")).upper() in {"OPEN", "CLOSED"}:
            events.append(_event(component, "POSITION_OPEN", "REGISTRY_OPEN", record, "opened_at"))
        if record.get("closed_at") or str(record.get("status", "")).upper() == "CLOSED":
            events.append(_event(component, "REGISTRY_CLOSE", "REGISTRY_CLOSE", record, "closed_at"))
    if component == "lifecycle":
        state = str(record.get("state") or record.get("current_state") or "").upper()
        if not any(item["event"] == "LIFECYCLE_FINISHED" for item in events) and _lifecycle_finished_evidence(record):
            events.append(_event(component, "LIFECYCLE_FINISHED", state, record))
    return events


def _deduplicate_extracted(events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    seen = set()
    result = []
    aliases: Dict[tuple[str, str, str], int] = {}
    for item in events:
        if (
            item["event"] in {"LIVE_ORDER_SENT", "BROKER_ACK"}
            and item.get("fact_order_id")
            and item.get("raw_event") in {
                "PLACE_MARKET_ORDER", "BROKER_LIVE_SENT",
                "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED",
            }
        ):
            alias_key = (item["component"], item["event"], str(item["fact_order_id"]))
            previous_index = aliases.get(alias_key)
            if previous_index is not None and result[previous_index].get("raw_event") != item.get("raw_event"):
                if item.get("raw_event") in {"BROKER_LIVE_SENT", "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED"}:
                    result[previous_index] = item
                continue
            aliases.setdefault(alias_key, len(result))
        key = (item["component"], item["event"], item.get("event_id"), item.get("timestamp"), tuple(item.get("identifiers") or ()))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _duplicates(events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    groups: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
    for item in events:
        # O mesmo fato em Registry, Lifecycle e Timeline e corroboracao entre
        # fontes, nao uma segunda acao operacional. Duplicidade e avaliada no
        # writer/componente que produziu o evento.
        groups.setdefault((item["event"], item["component"]), []).append(item)
    found = []
    for (name, component), items in groups.items():
        if len(items) < 2:
            continue
        if name in REPEATABLE_EVENTS or name in OBSERVATIONAL_META_EVENTS:
            fingerprints = {}
            for item in items:
                fingerprint = item.get("event_id") or (item.get("component"), item.get("timestamp"), item.get("raw_event"))
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
            count = sum(value - 1 for value in fingerprints.values() if value > 1)
            if not count:
                continue
        else:
            count = len(items) - 1
        found.append({"event": name, "occurrences": len(items), "duplicates": count, "components": [component]})
    return found


def _chronology(events: list[Dict[str, Any]]) -> Dict[str, Any]:
    index = {name: position for position, name in enumerate(EVENT_ORDER)}
    timestamped = sorted((item for item in events if item.get("epoch") is not None), key=lambda item: item["epoch"])
    violations = []
    highest = -1
    previous = None
    for item in timestamped:
        if item["event"] in OBSERVATIONAL_META_EVENTS:
            continue
        current = index.get(item["event"], highest)
        if current < highest and item["event"] not in REPEATABLE_EVENTS:
            violations.append({"event": item["event"], "timestamp": item["timestamp"], "after": previous})
        if current > highest:
            highest = current
            previous = item["event"]
    ordered = [{k: item.get(k) for k in ("event", "component", "timestamp", "event_id")} for item in timestamped]
    return {"ordered": not violations, "violations": violations, "events": ordered, "events_without_timestamp": sum(1 for item in events if item.get("epoch") is None)}


def _latencies(events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    timestamped = sorted((item for item in events if item.get("epoch") is not None and item["event"] not in OBSERVATIONAL_META_EVENTS), key=lambda item: item["epoch"])
    result = []
    for before, after in zip(timestamped, timestamped[1:]):
        result.append({"from": before["event"], "to": after["event"], "latency_ms": round((after["epoch"] - before["epoch"]) * 1000, 3)})
    return result


def _row_value(records: list[Mapping[str, Any]], *keys: str) -> Any:
    for record in reversed(records):
        for container in (record, record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}):
            for key in keys:
                if container.get(key) not in (None, ""):
                    return container.get(key)
    return None


def _row_value_by_alias(records: list[Mapping[str, Any]], *keys: str) -> Any:
    """Honor canonical alias precedence across root and direct metadata."""
    for key in keys:
        for record in reversed(records):
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            for container in (record, metadata):
                if container.get(key) not in (None, ""):
                    return container.get(key)
    return None


def _registry_quantity(records: list[Mapping[str, Any]]) -> Any:
    remaining = _row_value_by_alias(records, "remaining_quantity", "remaining_qty", "quantity_open", "open_qty")
    if remaining not in (None, ""):
        return remaining
    return _row_value_by_alias(records, "initial_quantity", "initial_qty", "original_quantity", "quantity", "qty")


def _broker_quantity(records: list[Mapping[str, Any]]) -> Any:
    reduction_observed = any(
        _record_event_name(record) in {
            "TP50_FILL_RECORDED", "TP50_CONFIRMED", "PARTIAL_CLOSE",
            "CLOSE_FILL_RECORDED", "CLOSE_PARTIAL_RECORDED", "CLOSE_CONFIRMED",
            "LIVE_TRADE_CLOSED",
        }
        for record in records
    )
    for record in reversed(records):
        raw = _record_event_name(record)
        if "DISASTER_STOP" in raw:
            continue
        contracts = _direct_value(record, "contracts")
        if contracts not in (None, ""):
            return contracts
    if not reduction_observed:
        for record in reversed(records):
            raw = _record_event_name(record)
            if raw in {
                "BROKER_LIVE_SENT", "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED",
                "PLACE_MARKET_ORDER",
            } and _confirmed_broker_send(record):
                value = _direct_value(record, "contracts", "quantity", "qty", "amount")
                if value not in (None, ""):
                    return value
    for record in reversed(records):
        raw = _record_event_name(record)
        position_fact = _direct_value(record, "position_found") is True or str(_direct_value(record, "position_status") or "").upper() in {"OPEN", "ACTIVE"}
        if position_fact and "DISASTER_STOP" not in raw:
            value = _direct_value(record, "quantity", "qty")
            if value not in (None, ""):
                return value
    return None


def _facts(records: list[Mapping[str, Any]], component: str) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    if component == "registry":
        facts["status"] = _row_value(records, "status")
        facts["quantity"] = _registry_quantity(records)
    elif component == "broker":
        facts["status"] = _row_value(records, "position_status")
        if facts["status"] in (None, ""):
            for record in reversed(records):
                if _direct_value(record, "position_found") is not None:
                    facts["status"] = _direct_value(record, "status")
                    break
        facts["quantity"] = _broker_quantity(records)
    elif component == "shadow_runtime":
        facts["status"] = _row_value(records, "state", "current_state", "lifecycle_state")
        facts["quantity"] = _row_value(records, "quantity_open", "quantity", "qty", "filled")
    else:
        facts["status"] = _row_value(records, "status", "state", "current_state")
        facts["quantity"] = _row_value(records, "quantity_open", "quantity", "qty", "filled")
    facts.update({
        "symbol": _row_value(records, "symbol"),
        "side": _row_value(records, "position_side", "side"),
        "entry": _row_value(records, "entry", "entry_price", "average_price", "avg_price", "price_ref"),
        "exit": _row_value(records, "exit_price", "close_price", "exit"),
    })
    return {key: value for key, value in facts.items() if value not in (None, "")}


def _equal_fact(left: Any, right: Any, field: Optional[str] = None) -> bool:
    if field == "symbol":
        return _normalize_symbol(left) == _normalize_symbol(right)
    if field == "side":
        return _normalize_side(left) == _normalize_side(right)
    try:
        a, b = float(left), float(right)
        tolerance = ENTRY_REFERENCE_TOLERANCE_RATIO if field == "entry" else 1e-8
        return abs(a - b) <= max(1e-8, max(abs(a), abs(b)) * tolerance)
    except (TypeError, ValueError):
        aliases = {"FILLED": "OPEN", "OPENED": "OPEN", "FINISHED": "CLOSED", "CLOSE_CONFIRMED": "CLOSED", "OUTCOME_RECORDED": "CLOSED"}
        a = aliases.get(str(left).upper(), str(left).upper())
        b = aliases.get(str(right).upper(), str(right).upper())
        return a == b


def _compare(left_name: str, right_name: str, facts: Mapping[str, Mapping[str, Any]]) -> list[Dict[str, Any]]:
    left, right = facts.get(left_name, {}), facts.get(right_name, {})
    result = []
    for field in sorted(set(left) & set(right)):
        if not _equal_fact(left[field], right[field], field):
            result.append({"components": [left_name, right_name], "field": field, "left": _json_safe(left[field]), "right": _json_safe(right[field])})
    return result


class TradeTimelineValidator:
    """Validador read-only. Excecoes de fontes sao convertidas em evidencia."""

    def __init__(self, sources: Optional[Mapping[str, Any]] = None, logger: Optional[logging.Logger] = None):
        self.sources = dict(sources) if sources is not None else build_default_sources()
        self.logger = logger or LOGGER

    def validate(self, trade_id: str) -> Dict[str, Any]:
        started = time.perf_counter()
        identity = str(trade_id or "").strip()
        _structured_log(self.logger, "info", "TRADE_TIMELINE_VALIDATION_BEGIN", trade_id=identity)
        components: Dict[str, Dict[str, Any]] = {}
        records: Dict[str, list[Mapping[str, Any]]] = {}
        errors = []
        warnings = []
        correlation = new_correlation_context(identity)

        if not identity:
            errors.append({"component": "validator", "error_type": "ValueError", "message": "trade_id is required"})

        for name in COMPONENTS:
            source = self.sources.get(name)
            if source is None:
                components[name] = {"status": "UNAVAILABLE", "records": 0}
                records[name] = []
                continue
            try:
                value = source(identity) if callable(source) else source
                rows = correlate_source_records(name, _coerce_records(value), correlation)
                reader_metadata = _reader_metadata(value)
                records[name] = rows
                fully_corrupt = bool(
                    reader_metadata.get("files_read", 0) > 0
                    and reader_metadata.get("lines_scanned", 0) > 0
                    and reader_metadata.get("valid_lines", 0) == 0
                    and reader_metadata.get("invalid_lines", 0) > 0
                )
                status = "AVAILABLE" if rows else ("DEGRADED" if fully_corrupt else "NO_EVIDENCE")
                components[name] = {"status": status, "records": len(rows), **reader_metadata}
                if reader_metadata.get("invalid_lines", 0) > 0:
                    warnings.append({
                        "component": name,
                        "code": "CORRUPT_JSONL_LINES_SKIPPED",
                        "count": reader_metadata["invalid_lines"],
                    })
                _structured_log(
                    self.logger,
                    "info",
                    "TRADE_TIMELINE_SOURCE_READ",
                    trade_id=identity,
                    component=name,
                    status=status,
                    records=len(rows),
                    invalid_lines=reader_metadata.get("invalid_lines", 0),
                    partial=reader_metadata.get("partial", False),
                )
            except Exception as exc:
                records[name] = []
                components[name] = {"status": "ERROR", "records": 0, "error_type": type(exc).__name__, "error": str(exc)[:300]}
                errors.append({"component": name, "error_type": type(exc).__name__, "message": str(exc)[:300]})
                _structured_log(self.logger, "warning", "TRADE_TIMELINE_SOURCE_ERROR", trade_id=identity, component=name, error_type=type(exc).__name__)

        events = []
        for component, rows in records.items():
            for record in rows:
                events.extend(_events_from_record(component, record))
        events = _deduplicate_extracted(events)
        events.sort(key=lambda item: (item.get("epoch") is None, item.get("epoch") or 0.0, EVENT_ORDER.index(item["event"]) if item["event"] in EVENT_ORDER else 999))

        present = {item["event"] for item in events}
        missing = [name for name in REQUIRED_EVENTS if name not in present]
        duplicates = _duplicates(events)
        chronology = _chronology(events)
        facts = {name: _facts(rows, name) for name, rows in records.items()}
        divergences = _compare("registry", "broker", facts) + _compare("lifecycle", "shadow_runtime", facts)
        timeline_absent = components["timeline"]["status"] != "AVAILABLE"
        validation_errors = bool(errors or missing or duplicates or divergences or not chronology["ordered"] or timeline_absent or not identity)
        result = "FAIL" if validation_errors else "PASS"

        report = {
            "ok": True,
            "module": "trade_timeline_validator",
            "version": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trade_id": identity,
            "result": result,
            "valid": result == "PASS",
            "audit_only": True,
            "fail_open": True,
            "production_blocked": False,
            "authorities": {
                "write_access": False,
                "registry_write_access": False,
                "lifecycle_write_access": False,
                "broker_access": False,
                "execution_control": False,
                "telegram_send_access": False,
            },
            "components": components,
            "events_found": events,
            "events_missing": missing,
            "events_duplicated": duplicates,
            "chronology": chronology,
            "latencies": _latencies(events),
            "divergences": divergences,
            "warnings": warnings,
            "errors": errors,
            "summary": {
                "events_found": len(events),
                "events_missing": len(missing),
                "duplicate_groups": len(duplicates),
                "divergences": len(divergences),
                "component_errors": len(errors),
                "warnings": len(warnings),
                "timeline_available": not timeline_absent,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }
        _structured_log(self.logger, "info" if result == "PASS" else "warning", "TRADE_TIMELINE_VALIDATION_END", trade_id=identity, result=result, **report["summary"])
        return report


def validate_trade_timeline(trade_id: str, *, sources: Optional[Mapping[str, Any]] = None, logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """API publica fail-open para validacao de um trade."""
    try:
        return TradeTimelineValidator(sources=sources, logger=logger).validate(trade_id)
    except Exception as exc:  # ultima barreira: auditoria nunca afeta a operacao
        active_logger = logger or LOGGER
        _structured_log(active_logger, "exception", "TRADE_TIMELINE_VALIDATION_ERROR", trade_id=str(trade_id or ""), error_type=type(exc).__name__)
        return {
            "ok": True,
            "module": "trade_timeline_validator",
            "version": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trade_id": str(trade_id or ""),
            "result": "FAIL",
            "valid": False,
            "audit_only": True,
            "fail_open": True,
            "production_blocked": False,
            "errors": [{"component": "validator", "error_type": type(exc).__name__, "message": str(exc)[:300]}],
        }


__all__ = [
    "COMPONENTS",
    "EVENT_ORDER",
    "REQUIRED_EVENTS",
    "CorrelationContext",
    "TradeTimelineValidator",
    "build_default_sources",
    "correlate_source_records",
    "default_source_paths",
    "new_correlation_context",
    "validate_trade_timeline",
]
