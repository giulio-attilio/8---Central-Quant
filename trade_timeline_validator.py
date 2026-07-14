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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional


VERSION = "2026-07-13-TRADE-TIMELINE-VALIDATOR-V1"
LOGGER = logging.getLogger(__name__)

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
    "MATCH": "SHADOW_VALIDATED",
    "RECONCILIATION_COMPLETED": "SHADOW_VALIDATED",
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
    "order_id",
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


def default_source_paths(environ: Optional[Mapping[str, str]] = None) -> Dict[str, tuple[Path, ...]]:
    root = _data_dir(environ)
    return {
        "registry": (Path((environ or os.environ).get("TRADE_REGISTRY_FILE", root / "trade_registry.json")),),
        "lifecycle": (root / "trade_lifecycle_shadow_snapshot.json", root / "trade_lifecycle_shadow_events.jsonl"),
        "history_manager": (root / "history_events.jsonl",),
        "execution_engine": (root / "execution_engine_log.jsonl", root / "execution_audit_log.jsonl"),
        "execution_orchestrator": (root / "execution_orchestrator_log.jsonl",),
        "broker": (root / "broker_executions_log.jsonl", root / "broker_execution_audit_log.jsonl"),
        "shadow_runtime": (root / "trade_lifecycle_shadow_runtime_events.jsonl", root / "trade_lifecycle_shadow_runtime_divergences.jsonl"),
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


def _identity_values(record: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for item in _walk_dicts(record):
        for key, value in item.items():
            if str(key).lower() in IDENTITY_KEYS and value not in (None, ""):
                values.add(str(value).strip())
    return values


def _matches(record: Mapping[str, Any], identifiers: set[str]) -> bool:
    return bool(_identity_values(record) & identifiers)


def _read_path(path: Path) -> Iterable[Mapping[str, Any]]:
    if not path.exists() or not path.is_file():
        return
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, Mapping):
                    yield item
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, Mapping):
        yield data
    elif isinstance(data, list):
        yield from (item for item in data if isinstance(item, Mapping))


def _registry_records(data: Mapping[str, Any], identifiers: set[str]) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    opened = data.get("open_trades")
    if isinstance(opened, Mapping):
        candidates.extend(item for item in opened.values() if isinstance(item, Mapping))
    closed = data.get("closed_trades")
    if isinstance(closed, list):
        candidates.extend(item for item in closed if isinstance(item, Mapping))
    if data.get("trade") and isinstance(data["trade"], Mapping):
        candidates.append(data["trade"])
    if not candidates:
        candidates.append(data)
    return [item for item in candidates if _matches(item, identifiers)]


def _default_reader(component: str, paths: tuple[Path, ...], shared_identifiers: Optional[set[str]] = None) -> Callable[[str], list[Mapping[str, Any]]]:
    def read(trade_id: str) -> list[Mapping[str, Any]]:
        identifiers = shared_identifiers if shared_identifiers is not None else set()
        identifiers.add(str(trade_id).strip())
        matched: list[Mapping[str, Any]] = []
        for path in paths:
            for row in _read_path(path):
                if component == "registry":
                    found = _registry_records(row, identifiers)
                    matched.extend(found)
                    for item in found:
                        identifiers.update(_identity_values(item))
                elif _matches(row, identifiers):
                    matched.append(row)
                    identifiers.update(_identity_values(row))
        return matched

    return read


def build_default_sources(environ: Optional[Mapping[str, str]] = None) -> Dict[str, Callable[[str], list[Mapping[str, Any]]]]:
    """Constroi leitores locais. Nao le arquivos ate a validacao ser solicitada."""
    identifiers: set[str] = set()
    return {name: _default_reader(name, paths, identifiers) for name, paths in default_source_paths(environ).items()}


def _coerce_records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("records", "items", "events", "lifecycles"):
            if isinstance(value.get(key), list):
                head = {k: v for k, v in value.items() if k != key}
                rows = [item for item in value[key] if isinstance(item, Mapping)]
                return ([head] if head else []) + rows
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


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
    for item in _walk_dicts(record):
        for key in ("event_type", "event", "action", "type"):
            if item.get(key) not in (None, ""):
                return str(item[key]).upper().strip().replace(" ", "_")
    return ""


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

    raw = _raw_event(record)
    canonical = EVENT_ALIASES.get(raw)
    if canonical:
        events.append(_event(component, canonical, raw, record))

    if component == "registry":
        if record.get("opened_at") or str(record.get("status", "")).upper() in {"OPEN", "CLOSED"}:
            events.append(_event(component, "POSITION_OPEN", "REGISTRY_OPEN", record, "opened_at"))
        if record.get("closed_at") or str(record.get("status", "")).upper() == "CLOSED":
            events.append(_event(component, "REGISTRY_CLOSE", "REGISTRY_CLOSE", record, "closed_at"))
    if component == "lifecycle":
        state = str(record.get("state") or record.get("current_state") or "").upper()
        if state in {"OUTCOME_RECORDED", "LEARNING_ELIGIBLE"}:
            events.append(_event(component, "LIFECYCLE_FINISHED", state, record))
    if component == "shadow_runtime":
        status = str(record.get("status") or record.get("comparison") or "").upper()
        if status in {"MATCH", "APPLIED", "EVENT_APPLIED"}:
            events.append(_event(component, "SHADOW_VALIDATED", status, record))
    return events


def _deduplicate_extracted(events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    seen = set()
    result = []
    for item in events:
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
        if name in REPEATABLE_EVENTS:
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
        current = index.get(item["event"], highest)
        if current < highest and item["event"] not in REPEATABLE_EVENTS:
            violations.append({"event": item["event"], "timestamp": item["timestamp"], "after": previous})
        if current > highest:
            highest = current
            previous = item["event"]
    ordered = [{k: item.get(k) for k in ("event", "component", "timestamp", "event_id")} for item in timestamped]
    return {"ordered": not violations, "violations": violations, "events": ordered, "events_without_timestamp": sum(1 for item in events if item.get("epoch") is None)}


def _latencies(events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    timestamped = sorted((item for item in events if item.get("epoch") is not None), key=lambda item: item["epoch"])
    result = []
    for before, after in zip(timestamped, timestamped[1:]):
        result.append({"from": before["event"], "to": after["event"], "latency_ms": round((after["epoch"] - before["epoch"]) * 1000, 3)})
    return result


def _facts(records: list[Mapping[str, Any]]) -> Dict[str, Any]:
    aliases = {
        "status": ("status", "state", "current_state"),
        "symbol": ("symbol",),
        "side": ("side", "position_side"),
        "entry": ("entry", "entry_price", "average_price", "avg_price"),
        "exit": ("exit_price", "close_price", "exit"),
        "quantity": ("quantity_open", "quantity", "qty", "filled", "amount"),
    }
    facts: Dict[str, Any] = {}
    for record in records:
        for item in _walk_dicts(record):
            for canonical, keys in aliases.items():
                for key in keys:
                    if item.get(key) not in (None, ""):
                        facts[canonical] = item[key]
                        break
    return facts


def _equal_fact(left: Any, right: Any) -> bool:
    try:
        a, b = float(left), float(right)
        return abs(a - b) <= max(1e-8, max(abs(a), abs(b)) * 1e-8)
    except (TypeError, ValueError):
        aliases = {"FILLED": "OPEN", "OPENED": "OPEN", "FINISHED": "CLOSED", "CLOSE_CONFIRMED": "CLOSED", "OUTCOME_RECORDED": "CLOSED"}
        a = aliases.get(str(left).upper(), str(left).upper())
        b = aliases.get(str(right).upper(), str(right).upper())
        return a == b


def _compare(left_name: str, right_name: str, facts: Mapping[str, Mapping[str, Any]]) -> list[Dict[str, Any]]:
    left, right = facts.get(left_name, {}), facts.get(right_name, {})
    result = []
    for field in sorted(set(left) & set(right)):
        if not _equal_fact(left[field], right[field]):
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
                rows = _coerce_records(value)
                records[name] = rows
                components[name] = {"status": "AVAILABLE" if rows else "NO_EVIDENCE", "records": len(rows)}
                _structured_log(self.logger, "info", "TRADE_TIMELINE_SOURCE_READ", trade_id=identity, component=name, status=components[name]["status"], records=len(rows))
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
        facts = {name: _facts(rows) for name, rows in records.items()}
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
            "errors": errors,
            "summary": {
                "events_found": len(events),
                "events_missing": len(missing),
                "duplicate_groups": len(duplicates),
                "divergences": len(divergences),
                "component_errors": len(errors),
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
    "TradeTimelineValidator",
    "build_default_sources",
    "default_source_paths",
    "validate_trade_timeline",
]
