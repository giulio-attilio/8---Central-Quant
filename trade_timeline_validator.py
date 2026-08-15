"""Trade Timeline Validator V1.

Camada estritamente observacional para reconstruir e validar a linha temporal de
um trade. O modulo nao importa componentes operacionais: as fontes padrao sao
arquivos locais lidos sob demanda e fontes alternativas podem ser injetadas.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from trade_evidence_physical_window_contract_v1 import (
    BLOCK_BYTES as PHYSICAL_BLOCK_BYTES,
    BYTE_BUDGET as PHYSICAL_BYTE_BUDGET,
    CURSOR_CONTRACT_VERSION as PHYSICAL_CURSOR_CONTRACT_VERSION,
    RECORD_BUDGET as PHYSICAL_RECORD_BUDGET,
    TIMESTAMP_KEYS as PHYSICAL_TIMESTAMP_KEYS,
    cursor_targets_path as _physical_cursor_targets_path,
    decode_scan_cursor as _physical_decode_scan_cursor,
    encode_scan_cursor as _physical_encode_scan_cursor,
    first_timestamp as _physical_first_timestamp,
    parse_timestamp as _physical_parse_timestamp,
    path_fingerprint as _physical_path_fingerprint,
)


VERSION = "2026-08-14-TRADE-TIMELINE-RECENT-IDENTITY-SCAN-V1"
LOGGER = logging.getLogger(__name__)
JSONL_MAX_BYTES = PHYSICAL_BYTE_BUDGET
JSONL_MAX_VALID_LINES = PHYSICAL_RECORD_BUDGET
JSONL_BLOCK_BYTES = PHYSICAL_BLOCK_BYTES
JSONL_CURSOR_VERSION = PHYSICAL_CURSOR_CONTRACT_VERSION
CORRELATION_PRE_OPEN_SECONDS = 15 * 60
CORRELATION_POST_CLOSE_SECONDS = 24 * 60 * 60
ENTRY_REFERENCE_TOLERANCE_RATIO = 0.001
IDENTITY_CANDIDATE_LIMIT = 20
_INDEX_SHADOW_COMPONENTS = frozenset({"history_manager", "timeline"})

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
    "registry_record_id",
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
    "registry_record_id": "registry_id",
    "tradelifecycleid": "lifecycle_id",
    "trade_lifecycle_id": "lifecycle_id",
    "position_uuid": "trade_uuid",
    # Canonical Falcon stop IDs are persisted under stop-specific field names
    # by the position/Registry projections.  Normalize those names into the
    # client-order identity group so an opaque FDS1 hash is correlated only by
    # exact equality.  Unlike the historical ``*-DS`` format, an FDS1 value is
    # never reconstructed from (or prefix-matched against) the entry ID.
    "broker_stop_client_order_id": "client_order_id",
    "brokerstopclientorderid": "client_order_id",
    "disaster_stop_client_order_id": "client_order_id",
    "disasterstopclientorderid": "client_order_id",
    "falcon_disaster_stop_client_order_id": "client_order_id",
    "falcondisasterstopclientorderid": "client_order_id",
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

STRONG_IDENTITY_GROUPS = {
    "trade_uuid",
    "registry",
    "lifecycle",
    "client_order",
    "order",
    "fill",
}
SECONDARY_IDENTITY_GROUPS = {"execution", "decision", "signal", "trade"}

TIMESTAMP_KEYS = PHYSICAL_TIMESTAMP_KEYS


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


def _legacy_derived_stop_client_id_matches_parent(value: str, parent: str) -> bool:
    """Recognize the historical sliced ``-DS`` format without generating it."""

    derived = str(value or "").upper().strip()
    trusted_parent = str(parent or "").upper().strip()
    if not derived.endswith("-DS"):
        return False
    legacy_prefix = derived.removesuffix("-DS")
    return bool(
        len(legacy_prefix) == 24
        and trusted_parent.startswith(legacy_prefix)
    )


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
    return any(
        _legacy_derived_stop_client_id_matches_parent(child, parent)
        for child in supplied
        for parent in parents
    )


@dataclass(frozen=True)
class TargetIdentity:
    """Immutable view of the identity currently proven for one trade instance."""

    trade_id: str
    strong: Dict[str, frozenset[str]]
    secondary: Dict[str, frozenset[str]]
    registry_anchored: bool
    ambiguous: bool


@dataclass
class CorrelationContext:
    """Typed, rejection-first correlation state shared by read-only sources."""

    trade_id: str
    trusted: Dict[str, set[str]] = field(default_factory=dict)
    trusted_typed: Dict[str, set[str]] = field(default_factory=dict)
    profile: Dict[str, Optional[str]] = field(default_factory=lambda: {"bot": None, "setup": None, "symbol": None, "side": None})
    opened_epoch: Optional[float] = None
    closed_epoch: Optional[float] = None
    registry_anchored: bool = False
    identity_ambiguous: bool = False
    requested_opened_at: Optional[str] = None
    requested_opened_epoch: Optional[float] = None
    requested_instance_id: Optional[str] = None
    registry_candidate_count: int = 0
    registry_candidates: list[Dict[str, Any]] = field(default_factory=list)
    registry_candidates_truncated: bool = False
    registry_selection_basis: Optional[str] = None

    def __post_init__(self) -> None:
        self.trusted.setdefault("trade", set()).add(self.trade_id)
        self.trusted_typed.setdefault("trade_id", set()).add(self.trade_id)


@dataclass(frozen=True)
class EvidenceBundle:
    """Request-local correlated evidence, treated as immutable after build."""

    trade_id: str
    target_identity: TargetIdentity
    registry_resolution: Mapping[str, Any]
    records: Mapping[str, tuple[Mapping[str, Any], ...]]
    raw_sources: Mapping[str, Any]
    source_coverage: Mapping[str, Mapping[str, Any]]
    component_status: Mapping[str, Mapping[str, Any]]
    events: tuple[Mapping[str, Any], ...]
    matched_identifiers: Mapping[str, tuple[str, ...]]
    source_fingerprints: Mapping[str, Mapping[str, int]]
    warnings: tuple[Mapping[str, Any], ...]
    errors: tuple[Mapping[str, Any], ...]
    correlation: CorrelationContext = field(repr=False, compare=False)


def _normalize_opened_selectors(
    opened_at: Any = None,
    opened_epoch: Any = None,
) -> tuple[Optional[str], Optional[float]]:
    normalized_at = None
    if opened_at not in (None, ""):
        normalized_at = str(opened_at).strip()
        parsed_at, _ = _parse_timestamp(normalized_at)
        if parsed_at is None:
            raise ValueError("invalid opened_at selector")
    parsed_epoch = None
    if opened_epoch not in (None, ""):
        try:
            parsed_epoch = float(opened_epoch)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid opened_epoch selector") from exc
        if not math.isfinite(parsed_epoch):
            raise ValueError("invalid opened_epoch selector")
    return normalized_at, parsed_epoch


def new_correlation_context(
    trade_id: str,
    *,
    opened_at: Any = None,
    opened_epoch: Any = None,
    instance_id: Any = None,
) -> CorrelationContext:
    normalized_instance = str(instance_id or "").strip() or None
    normalized_opened_at, normalized_opened_epoch = _normalize_opened_selectors(
        opened_at,
        opened_epoch,
    )
    return CorrelationContext(
        str(trade_id or "").strip(),
        requested_opened_at=normalized_opened_at,
        requested_opened_epoch=normalized_opened_epoch,
        requested_instance_id=normalized_instance,
    )


def target_identity_from_context(context: CorrelationContext) -> TargetIdentity:
    strong_groups = set(STRONG_IDENTITY_GROUPS)
    return TargetIdentity(
        trade_id=context.trade_id,
        strong={
            group: frozenset(context.trusted.get(group, set()))
            for group in sorted(strong_groups)
            if context.trusted.get(group)
        },
        secondary={
            group: frozenset(context.trusted.get(group, set()))
            for group in sorted(SECONDARY_IDENTITY_GROUPS - strong_groups)
            if context.trusted.get(group)
        },
        registry_anchored=context.registry_anchored,
        ambiguous=context.identity_ambiguous,
    )


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
    if (
        not context.registry_anchored
        and (
            context.requested_opened_at
            or context.requested_opened_epoch is not None
            or context.requested_instance_id
        )
    ):
        # A timestamp scopes a Registry occurrence but cannot prove ownership
        # by itself.  Never fall back to logical-ID-only journal matching when
        # the requested Registry instance was not resolved.
        return False
    grouped = _grouped_identities(record)
    target = target_identity_from_context(context)
    explicit_trade_ids = _identity_pairs(record).get("trade_id", set())
    if explicit_trade_ids and explicit_trade_ids != {context.trade_id}:
        return False
    if _profile_conflicts(record, component, context) or _time_conflicts(record, context):
        return False

    exact_trade = context.trade_id in explicit_trade_ids
    strong_match = False
    secondary_match = False
    for group, supplied in grouped.items():
        known = set(target.strong.get(group, frozenset()))
        if not known:
            known = set(target.secondary.get(group, frozenset()))
        if group == "client_order":
            supplied = {value for value in supplied if not _is_derived_stop_client_id(value)}
        if known & supplied:
            if group in target.strong:
                strong_match = True
            else:
                secondary_match = True
    derived_stop_match = _strict_derived_stop_relation(record, component, grouped, context)
    if not (exact_trade or strong_match or secondary_match or derived_stop_match):
        return False
    if _has_scoped_identity_conflict(record, context):
        return False
    if exact_trade and _unrelated_client_order(grouped, context):
        return False
    return True


def _promote_record(record: Mapping[str, Any], component: str, context: CorrelationContext) -> None:
    pairs = _identity_pairs(record)
    grouped = _grouped_identities(record)
    if component != "registry" and not context.registry_anchored:
        # A reusable logical trade_id can select records for observation, but it
        # cannot bootstrap new order/lifecycle identities.  Otherwise an older
        # instance could poison the context and pull in unrelated history.
        supplied_trade_ids = pairs.get("trade_id", set())
        if context.trade_id in supplied_trade_ids or any(
            context.trusted.get(group, set()) & values
            for group, values in grouped.items()
            if group in SECONDARY_IDENTITY_GROUPS
        ):
            context.identity_ambiguous = True
        for key, values in pairs.items():
            known = context.trusted_typed.get(key, set())
            if known:
                context.trusted_typed.setdefault(key, set()).update(known & values)
        for group, values in grouped.items():
            known = context.trusted.get(group, set())
            if known:
                context.trusted.setdefault(group, set()).update(known & values)
        return

    for key, values in pairs.items():
        context.trusted_typed.setdefault(key, set()).update(values)
    for group, values in grouped.items():
        safe_values = values
        if group == "client_order":
            safe_values = {value for value in values if not _is_derived_stop_client_id(value)}
        context.trusted.setdefault(group, set()).update(safe_values)
    if component == "registry":
        context.registry_anchored = True
        profile = _record_profile(record, component)
        for key, value in profile.items():
            if value:
                context.profile[key] = value
        opened_value = _direct_value(record, "opened_epoch", "opened_at")
        closed_value = _direct_value(record, "closed_epoch", "closed_at")
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
    elif isinstance(opened, list):
        candidates.extend(item for item in opened if isinstance(item, Mapping))
    closed = data.get("closed_trades")
    if isinstance(closed, Mapping):
        candidates.extend(item for item in closed.values() if isinstance(item, Mapping))
    elif isinstance(closed, list):
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


def _registry_opened_epoch(record: Mapping[str, Any]) -> Optional[float]:
    value = _direct_value(record, "opened_epoch")
    if value not in (None, ""):
        try:
            epoch = float(value)
        except (TypeError, ValueError):
            epoch = None
        if epoch is not None and math.isfinite(epoch):
            return epoch
    value = _direct_value(record, "opened_at")
    parsed, _ = _parse_timestamp(value) if value not in (None, "") else (None, None)
    return parsed


def _registry_opened_at_matches(record: Mapping[str, Any], requested: str) -> bool:
    candidate = _direct_value(record, "opened_at")
    if candidate not in (None, ""):
        if str(candidate).strip() == str(requested).strip():
            return True
        candidate_epoch, _ = _parse_timestamp(candidate)
        requested_epoch, _ = _parse_timestamp(requested)
        return bool(
            candidate_epoch is not None
            and requested_epoch is not None
            and abs(candidate_epoch - requested_epoch) <= 1.0
        )
    requested_epoch, _ = _parse_timestamp(requested)
    candidate_epoch = _registry_opened_epoch(record)
    return bool(
        candidate_epoch is not None
        and requested_epoch is not None
        and abs(candidate_epoch - requested_epoch) <= 1.0
    )


def _registry_instance_values(record: Mapping[str, Any]) -> set[str]:
    pairs = _identity_pairs(record)
    values: set[str] = set()
    for key, supplied in pairs.items():
        group = IDENTITY_GROUPS.get(key)
        if group in STRONG_IDENTITY_GROUPS and group != "trade":
            values.update(supplied)
    return values


def _registry_preferred_instance_id(record: Mapping[str, Any]) -> Optional[str]:
    pairs = _identity_pairs(record)
    for key in (
        "trade_uuid",
        "registry_id",
        "lifecycle_id",
        "client_order_id",
        "exchange_order_id",
        "broker_order_id",
        "order_id",
        "fill_id",
    ):
        values = sorted(pairs.get(key, set()))
        if values:
            return values[0]
    return None


def _registry_candidate_summary(record: Mapping[str, Any]) -> Dict[str, Any]:
    opened_epoch = _registry_opened_epoch(record)
    closed_value = _direct_value(record, "closed_at")
    closed_epoch_value = _direct_value(record, "closed_epoch")
    closed_epoch, _ = _parse_timestamp(
        closed_epoch_value if closed_epoch_value not in (None, "") else closed_value
    ) if closed_value not in (None, "") or closed_epoch_value not in (None, "") else (None, None)
    profile = _record_profile(record, "registry")
    return {
        "trade_id": str(_direct_value(record, "trade_id") or "").strip() or None,
        "instance_id": _registry_preferred_instance_id(record),
        "opened_at": _direct_value(record, "opened_at"),
        "opened_epoch": opened_epoch,
        "closed_at": closed_value,
        "closed_epoch": closed_epoch,
        "status": str(_direct_value(record, "status") or "").upper().strip() or None,
        **profile,
    }


def _reusable_logical_trade_id(trade_id: str, records: Iterable[Mapping[str, Any]]) -> bool:
    text = str(trade_id or "").upper().strip()
    prefix = text.split(":", 1)[0]
    if prefix.startswith("TURTLE"):
        return True
    for row in records:
        bot = str(_direct_value(row, "bot", "bot_name") or "").upper().strip()
        logical = str(_direct_value(row, "logical_trade_id") or "").upper().strip()
        reusable = _direct_value(row, "trade_id_reusable", "reusable_trade_id")
        if bot.startswith("TURTLE") or logical == text or _true(reusable):
            return True
    return False


def _set_registry_candidates(context: CorrelationContext, records: list[Mapping[str, Any]]) -> None:
    context.registry_candidate_count = len(records)
    context.registry_candidates = [
        _registry_candidate_summary(row)
        for row in records[:IDENTITY_CANDIDATE_LIMIT]
    ]
    context.registry_candidates_truncated = len(records) > IDENTITY_CANDIDATE_LIMIT


def _resolve_registry_candidate(
    records: list[Mapping[str, Any]],
    context: CorrelationContext,
) -> Optional[Mapping[str, Any]]:
    _set_registry_candidates(context, records)
    selected = records
    basis_parts = []
    if context.requested_instance_id:
        selected = [row for row in selected if context.requested_instance_id in _registry_instance_values(row)]
        basis_parts.append("instance_id")
    if context.requested_opened_at:
        selected = [
            row for row in selected
            if _registry_opened_at_matches(row, context.requested_opened_at)
        ]
        basis_parts.append("opened_at")
    if context.requested_opened_epoch is not None:
        selected = [
            row for row in selected
            if (epoch := _registry_opened_epoch(row)) is not None
            and abs(epoch - context.requested_opened_epoch) <= 1.0
        ]
        basis_parts.append("opened_epoch")
    basis = "+".join(
        item
        for item in ("opened_at", "opened_epoch", "instance_id")
        if item in basis_parts
    ) or None
    if len(selected) == 1 and (basis or not _reusable_logical_trade_id(context.trade_id, records)):
        context.registry_selection_basis = basis or "unique_trade_id"
        _set_registry_candidates(context, selected)
        return selected[0]
    if len(selected) > 1 or (len(selected) == 1 and _reusable_logical_trade_id(context.trade_id, records)):
        context.identity_ambiguous = True
        context.registry_selection_basis = "ambiguous"
        _set_registry_candidates(context, selected)
    elif basis:
        context.registry_selection_basis = f"{basis}_not_found"
    return None


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
        selected = _resolve_registry_candidate(exact, context)
        if selected is None:
            return []
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
        "evidence_found": False,
        "coverage_complete": True,
        "conclusive": True,
        "records_examined": 0,
        "direction": "REVERSE",
        "time_range_scanned": {"oldest": None, "newest": None},
        "stop_reason": "NOT_SCANNED",
        "source_size_bytes": 0,
        "snapshot_eof": 0,
        "next_scan_cursor": None,
        "evidence_status": "COMPLETE_NO_EVIDENCE",
    }


def _merge_reader_metadata(target: Dict[str, Any], source: Mapping[str, Any]) -> None:
    for key in (
        "files_considered", "files_read", "lines_scanned", "valid_lines",
        "invalid_lines", "bytes_scanned", "records_examined",
        "source_size_bytes", "snapshot_eof",
    ):
        target[key] = int(target.get(key, 0) or 0) + int(source.get(key, 0) or 0)
    target["partial"] = bool(target.get("partial") or source.get("partial"))
    target["coverage_limited"] = bool(target.get("coverage_limited") or source.get("coverage_limited"))
    target["coverage_complete"] = bool(target.get("coverage_complete", True) and source.get("coverage_complete", True))
    target["conclusive"] = bool(target.get("conclusive", True) and source.get("conclusive", True))
    target["evidence_found"] = bool(target.get("evidence_found") or source.get("evidence_found"))
    target["direction"] = source.get("direction") or target.get("direction") or "REVERSE"
    source_range = source.get("time_range_scanned") if isinstance(source.get("time_range_scanned"), Mapping) else {}
    target_range = target.get("time_range_scanned") if isinstance(target.get("time_range_scanned"), Mapping) else {}
    oldest = [value for value in (target_range.get("oldest"), source_range.get("oldest")) if value]
    newest = [value for value in (target_range.get("newest"), source_range.get("newest")) if value]
    target["time_range_scanned"] = {
        "oldest": min(oldest) if oldest else None,
        "newest": max(newest) if newest else None,
    }
    source_reason = str(source.get("stop_reason") or "NOT_SCANNED")
    if source.get("partial") or target.get("stop_reason") in (None, "NOT_SCANNED"):
        target["stop_reason"] = source_reason
    if source.get("next_scan_cursor"):
        target["next_scan_cursor"] = source["next_scan_cursor"]


def _path_fingerprint(path: Path) -> str:
    return _physical_path_fingerprint(path)


def _encode_scan_cursor(
    path: Path,
    file_stat: os.stat_result,
    snapshot_eof: int,
    next_end: int,
    *,
    oversized_line: bool = False,
    coverage_tainted: bool = False,
) -> str:
    return _physical_encode_scan_cursor(
        path,
        file_stat,
        snapshot_eof,
        next_end,
        oversized_line=oversized_line,
        coverage_tainted=coverage_tainted,
        cursor_version=JSONL_CURSOR_VERSION,
    )


def _decode_scan_cursor(token: str) -> Dict[str, Any]:
    return _physical_decode_scan_cursor(
        token,
        cursor_version=JSONL_CURSOR_VERSION,
    )


def _cursor_targets_path(decoded: Optional[Mapping[str, Any]], path: Path) -> bool:
    return _physical_cursor_targets_path(decoded, path)


def _mark_source_changed(stats: Dict[str, Any], source_size: int = 0) -> None:
    stats.update({
        "partial": True,
        "coverage_limited": True,
        "coverage_complete": False,
        "conclusive": False,
        "stop_reason": "SOURCE_CHANGED",
        "source_size_bytes": max(0, int(source_size)),
        "evidence_status": "SOURCE_CHANGED",
    })


def _update_scanned_time(stats: Dict[str, Any], record: Mapping[str, Any]) -> None:
    _epoch, normalized = _first_timestamp(record)
    if not normalized:
        return
    time_range = stats["time_range_scanned"]
    if time_range["oldest"] is None or normalized < time_range["oldest"]:
        time_range["oldest"] = normalized
    if time_range["newest"] is None or normalized > time_range["newest"]:
        time_range["newest"] = normalized


def _read_path(
    path: Path,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    scan_cursor: Optional[str] = None,
    capture_shadow_window: bool = False,
) -> Iterable[Mapping[str, Any]]:
    stats = metadata if metadata is not None else _new_reader_metadata()
    stats["files_considered"] = int(stats.get("files_considered", 0) or 0) + 1
    if path.suffix.lower() == ".jsonl":
        decoded_cursor = _decode_scan_cursor(scan_cursor) if scan_cursor else None
        try:
            path_stat = path.lstat()
        except FileNotFoundError:
            if decoded_cursor:
                _mark_source_changed(stats)
            else:
                stats["stop_reason"] = "SOURCE_MISSING"
            return
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise ValueError("JSONL source must be a regular non-symlink file")

        with path.open("rb") as handle:
            descriptor_stat = os.fstat(handle.fileno())
            if (
                int(descriptor_stat.st_dev) != int(path_stat.st_dev)
                or int(descriptor_stat.st_ino) != int(path_stat.st_ino)
                or not stat.S_ISREG(descriptor_stat.st_mode)
            ):
                _mark_source_changed(stats, int(descriptor_stat.st_size))
                return
            stats["files_read"] = int(stats.get("files_read", 0) or 0) + 1
            source_size = int(descriptor_stat.st_size)
            stats["source_size_bytes"] = source_size

            if decoded_cursor:
                if decoded_cursor["path"] != _path_fingerprint(path):
                    raise ValueError("scan cursor belongs to another source")
                if (
                    decoded_cursor["dev"] != int(descriptor_stat.st_dev)
                    or decoded_cursor["ino"] != int(descriptor_stat.st_ino)
                    or source_size < decoded_cursor["snapshot_eof"]
                ):
                    stats["snapshot_eof"] = decoded_cursor["snapshot_eof"]
                    _mark_source_changed(stats, source_size)
                    return
                snapshot_eof = decoded_cursor["snapshot_eof"]
                page_end = decoded_cursor["next_end"]
                if page_end > 0 and not decoded_cursor.get("oversized"):
                    handle.seek(page_end - 1, os.SEEK_SET)
                    if handle.read(1) != b"\n":
                        raise ValueError("scan cursor is not aligned to a physical line")
            else:
                snapshot_eof = source_size
                page_end = snapshot_eof
            stats["snapshot_eof"] = snapshot_eof
            shadow_window: Optional[Dict[str, Any]] = None
            if capture_shadow_window:
                try:
                    shadow_window = {
                        "path_fingerprint": _path_fingerprint(path),
                        "dev": int(descriptor_stat.st_dev),
                        "ino": int(descriptor_stat.st_ino),
                        "descriptor_size_at_open": source_size,
                        "descriptor_mtime_ns_at_open": int(descriptor_stat.st_mtime_ns),
                        "descriptor_ctime_ns_at_open": int(descriptor_stat.st_ctime_ns),
                        "snapshot_eof": int(snapshot_eof),
                        "page_end": int(page_end),
                        "page_start": None,
                        "cursor_tainted": bool(decoded_cursor and decoded_cursor.get("tainted")),
                        "cursor_oversized": bool(decoded_cursor and decoded_cursor.get("oversized")),
                        "source_changed": False,
                    }
                    stats["_shadow_physical_window"] = shadow_window
                except Exception:
                    shadow_window = None

            def source_changed_after_read() -> tuple[bool, os.stat_result]:
                final_descriptor = os.fstat(handle.fileno())
                try:
                    final_path = path.lstat()
                except FileNotFoundError:
                    final_path = None
                changed = bool(
                    final_path is None
                    or stat.S_ISLNK(final_path.st_mode)
                    or int(final_path.st_dev) != int(descriptor_stat.st_dev)
                    or int(final_path.st_ino) != int(descriptor_stat.st_ino)
                    or int(final_descriptor.st_size) < snapshot_eof
                )
                return changed, final_descriptor

            region_start = max(0, page_end - JSONL_MAX_BYTES)
            offset = page_end
            scan_chunks: list[bytes] = []
            bytes_read = 0
            short_read = False
            cursor_tainted = bool(decoded_cursor and decoded_cursor.get("tainted"))
            if decoded_cursor and decoded_cursor.get("oversized"):
                # This page ends in the middle of a line already proven larger
                # than MAX_BYTES. Skip backwards without ever parsing a fragment
                # as an independent JSON document.
                next_end = None
                while offset > region_start:
                    block_start = max(region_start, offset - JSONL_BLOCK_BYTES)
                    handle.seek(block_start, os.SEEK_SET)
                    chunk = handle.read(offset - block_start)
                    bytes_read += len(chunk)
                    if len(chunk) != offset - block_start:
                        short_read = True
                        break
                    preceding_newline = chunk.rfind(b"\n")
                    if preceding_newline >= 0:
                        next_end = block_start + preceding_newline + 1
                        break
                    offset = block_start
                stats["bytes_scanned"] = bytes_read
                stats.update({
                    "partial": True,
                    "coverage_limited": True,
                    "coverage_complete": False,
                    "conclusive": False,
                    "stop_reason": "LINE_EXCEEDS_BYTE_BUDGET",
                    "evidence_status": "COVERAGE_LIMITED",
                })
                if short_read:
                    _mark_source_changed(stats, int(os.fstat(handle.fileno()).st_size))
                elif next_end is not None:
                    stats["next_scan_cursor"] = _encode_scan_cursor(
                        path,
                        descriptor_stat,
                        snapshot_eof,
                        next_end,
                        coverage_tainted=True,
                    )
                elif region_start > 0:
                    stats["next_scan_cursor"] = _encode_scan_cursor(
                        path,
                        descriptor_stat,
                        snapshot_eof,
                        region_start,
                        oversized_line=True,
                        coverage_tainted=True,
                    )
                changed, final_descriptor = source_changed_after_read()
                if shadow_window is not None:
                    shadow_window.update({
                        "descriptor_size_after_read": int(final_descriptor.st_size),
                        "descriptor_mtime_ns_after_read": int(final_descriptor.st_mtime_ns),
                        "descriptor_ctime_ns_after_read": int(final_descriptor.st_ctime_ns),
                        "source_changed": bool(changed),
                        "oversized": True,
                    })
                if changed:
                    _mark_source_changed(stats, int(final_descriptor.st_size))
                    stats["next_scan_cursor"] = None
                return

            earliest_examined = page_end
            loaded_start = page_end
            record_budget_hit = False
            boundary_newline_seen = False
            carry = b""
            unresolved_parts: list[bytes] = []

            def examine_line(raw_line: bytes, absolute_start: int) -> bool:
                nonlocal earliest_examined
                earliest_examined = absolute_start
                stats["lines_scanned"] += 1
                if raw_line.strip():
                    stats["records_examined"] += 1
                return stats["records_examined"] >= JSONL_MAX_VALID_LINES

            while offset > region_start and not record_budget_hit:
                block_start = max(region_start, offset - JSONL_BLOCK_BYTES)
                handle.seek(block_start, os.SEEK_SET)
                chunk = handle.read(offset - block_start)
                bytes_read += len(chunk)
                if len(chunk) != offset - block_start:
                    short_read = True
                    break
                scan_chunks.append(chunk)
                loaded_start = block_start
                offset = block_start

                if b"\n" not in chunk:
                    if carry:
                        unresolved_parts.append(carry)
                        carry = b""
                    unresolved_parts.append(chunk)
                    continue

                combined = chunk
                if unresolved_parts:
                    combined += b"".join(reversed(unresolved_parts))
                    unresolved_parts = []
                else:
                    combined += carry
                carry = b""

                first_newline = combined.find(b"\n")
                boundary_newline_seen = True
                line_end = len(combined) - (1 if combined.endswith(b"\n") else 0)
                while line_end > first_newline:
                    previous_newline = combined.rfind(b"\n", first_newline + 1, line_end)
                    line_start = previous_newline + 1 if previous_newline > first_newline else first_newline + 1
                    if examine_line(combined[line_start:line_end], block_start + line_start):
                        record_budget_hit = (block_start + line_start) > 0
                        break
                    if previous_newline <= first_newline:
                        break
                    line_end = previous_newline
                carry = combined[:first_newline]

            if short_read:
                _mark_source_changed(stats, int(os.fstat(handle.fileno()).st_size))
                return

            if unresolved_parts:
                carry = b"".join(reversed(unresolved_parts))

            if not record_budget_hit and region_start == 0 and page_end > 0:
                if examine_line(carry, 0):
                    record_budget_hit = False  # exactly MAX_RECORDS at file start is complete

            stats["bytes_scanned"] = bytes_read
            next_end: Optional[int] = None
            if record_budget_hit:
                next_end = earliest_examined
                stats["stop_reason"] = "RECORD_BUDGET"
            elif region_start > 0:
                aligned_start = region_start + len(carry) + 1 if boundary_newline_seen else region_start
                if not boundary_newline_seen or aligned_start >= page_end:
                    stats.update({
                        "partial": True,
                        "coverage_limited": True,
                        "coverage_complete": False,
                        "conclusive": False,
                        "stop_reason": "LINE_EXCEEDS_BYTE_BUDGET",
                        "evidence_status": "COVERAGE_LIMITED",
                        "next_scan_cursor": _encode_scan_cursor(
                            path,
                            descriptor_stat,
                            snapshot_eof,
                            region_start,
                            oversized_line=True,
                            coverage_tainted=True,
                        ),
                    })
                    changed, final_descriptor = source_changed_after_read()
                    if shadow_window is not None:
                        shadow_window.update({
                            "descriptor_size_after_read": int(final_descriptor.st_size),
                            "descriptor_mtime_ns_after_read": int(final_descriptor.st_mtime_ns),
                            "descriptor_ctime_ns_after_read": int(final_descriptor.st_ctime_ns),
                            "source_changed": bool(changed),
                            "oversized": True,
                        })
                    if changed:
                        _mark_source_changed(stats, int(final_descriptor.st_size))
                        stats["next_scan_cursor"] = None
                    return
                next_end = aligned_start
                earliest_examined = aligned_start
                stats["stop_reason"] = "BYTE_BUDGET"
            else:
                earliest_examined = 0
                stats["stop_reason"] = "START_OF_SNAPSHOT"

            if next_end is not None and next_end > 0:
                stats.update({
                    "partial": True,
                    "coverage_limited": True,
                    "coverage_complete": False,
                    "conclusive": False,
                    "evidence_status": "COVERAGE_LIMITED",
                    "next_scan_cursor": _encode_scan_cursor(
                        path,
                        descriptor_stat,
                        snapshot_eof,
                        next_end,
                        # A continuation report does not carry records/events
                        # from newer pages, so it must never become conclusive
                        # merely because this page reaches byte zero.
                        coverage_tainted=True,
                    ),
                })

            if cursor_tainted:
                stats.update({
                    "partial": True,
                    "coverage_limited": True,
                    "coverage_complete": False,
                    "conclusive": False,
                    "evidence_status": "COVERAGE_LIMITED",
                })
                if next_end is None:
                    stats["stop_reason"] = "PRIOR_PAGE_COVERAGE_LIMITED"

            source_changed, final_descriptor_stat = source_changed_after_read()
            if shadow_window is not None:
                shadow_window.update({
                    "page_start": int(earliest_examined),
                    "descriptor_size_after_read": int(final_descriptor_stat.st_size),
                    "descriptor_mtime_ns_after_read": int(final_descriptor_stat.st_mtime_ns),
                    "descriptor_ctime_ns_after_read": int(final_descriptor_stat.st_ctime_ns),
                    "source_changed": bool(source_changed),
                    "oversized": False,
                })
            if source_changed:
                _mark_source_changed(stats, int(final_descriptor_stat.st_size))
                stats["next_scan_cursor"] = None

            # Reverse physical selection is deliberately replayed in file order
            # so correlation and identity promotion retain their old chronology.
            # Each selected physical line is decoded exactly once here. Chunks
            # are replayed incrementally to avoid a second page-sized byte copy.
            replay_offset = max(0, earliest_examined - loaded_start)

            def parse_replay_line(raw_line: bytes) -> Optional[Mapping[str, Any]]:
                if not raw_line.strip():
                    return None
                try:
                    item = json.loads(raw_line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    stats["invalid_lines"] += 1
                    return None
                stats["valid_lines"] += 1
                if isinstance(item, Mapping):
                    _update_scanned_time(stats, item)
                    return item
                return None

            pending_parts: list[bytes] = []
            first_chunk = True
            for replay_chunk in reversed(scan_chunks):
                if first_chunk:
                    replay_chunk = replay_chunk[replay_offset:]
                    first_chunk = False
                chunk_offset = 0
                while chunk_offset < len(replay_chunk):
                    newline = replay_chunk.find(b"\n", chunk_offset)
                    if newline < 0:
                        pending_parts.append(replay_chunk[chunk_offset:])
                        break
                    line_part = replay_chunk[chunk_offset:newline]
                    raw_line = (
                        b"".join((*pending_parts, line_part))
                        if pending_parts
                        else line_part
                    )
                    pending_parts.clear()
                    item = parse_replay_line(raw_line)
                    if item is not None:
                        yield item
                    chunk_offset = newline + 1
            if pending_parts:
                item = parse_replay_line(b"".join(pending_parts))
                if item is not None:
                    yield item
        return

    if not path.exists() or not path.is_file():
        stats["stop_reason"] = "SOURCE_MISSING"
        return
    stats["files_read"] = int(stats.get("files_read", 0) or 0) + 1
    file_size = path.stat().st_size
    stats.update({
        "bytes_scanned": file_size,
        "source_size_bytes": file_size,
        "snapshot_eof": file_size,
        "records_examined": 1,
        "direction": "FULL_DOCUMENT",
        "stop_reason": "FULL_DOCUMENT",
    })
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    stats["valid_lines"] = 1
    if isinstance(data, Mapping):
        yield data
    elif isinstance(data, list):
        yield from (item for item in data if isinstance(item, Mapping))


def identity_resolution_metadata(context: CorrelationContext) -> Dict[str, Any]:
    return {
        "registry_anchored": bool(context.registry_anchored),
        "ambiguous": bool(context.identity_ambiguous and not context.registry_anchored),
        "selection_basis": context.registry_selection_basis,
        "candidate_count": int(context.registry_candidate_count),
        "candidates": _json_safe(context.registry_candidates),
        "candidates_truncated": bool(context.registry_candidates_truncated),
    }


def apply_identity_resolution_metadata(context: CorrelationContext, value: Any) -> None:
    if not isinstance(value, Mapping) or not isinstance(value.get("_identity_metadata"), Mapping):
        return
    metadata = value["_identity_metadata"]
    if metadata.get("ambiguous") and not context.registry_anchored:
        context.identity_ambiguous = True
    try:
        candidate_count = int(metadata.get("candidate_count", 0) or 0)
    except (TypeError, ValueError):
        candidate_count = 0
    candidates = metadata.get("candidates")
    if candidate_count >= context.registry_candidate_count and isinstance(candidates, list):
        context.registry_candidate_count = candidate_count
        context.registry_candidates = [dict(row) for row in candidates if isinstance(row, Mapping)]
        context.registry_candidates_truncated = bool(metadata.get("candidates_truncated", False))
        context.registry_selection_basis = str(metadata.get("selection_basis") or "") or None


def _default_reader(
    component: str,
    paths: tuple[Path, ...],
    context: Optional[CorrelationContext] = None,
    scan_cursor: Optional[str] = None,
) -> Callable[[str], Dict[str, Any]]:
    def read(trade_id: str) -> Dict[str, Any]:
        active_context = context if context is not None else new_correlation_context(trade_id)
        capture_shadow = bool(
            component in _INDEX_SHADOW_COMPONENTS
            and str(os.environ.get("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "")).strip().lower()
            in {"1", "true", "yes", "on"}
            and str(os.environ.get("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", "")).strip().lower()
            in {"1", "true", "yes", "on"}
        )
        context_before = None
        if capture_shadow:
            try:
                context_before = copy.deepcopy(active_context)
            except Exception:
                capture_shadow = False
        shadow_legacy_started = time.perf_counter() if capture_shadow else None
        matched: list[Mapping[str, Any]] = []
        reader_metadata = _new_reader_metadata()
        physical_windows: list[Mapping[str, Any]] = []
        decoded_cursor = _decode_scan_cursor(scan_cursor) if scan_cursor else None
        for path in paths:
            path_metadata = _new_reader_metadata()
            path_cursor = scan_cursor if _cursor_targets_path(decoded_cursor, path) else None
            for row in _read_path(
                path,
                path_metadata,
                scan_cursor=path_cursor,
                capture_shadow_window=capture_shadow,
            ):
                matched.extend(correlate_source_records(component, (row,), active_context))
            if isinstance(path_metadata.get("_shadow_physical_window"), Mapping):
                physical_windows.append(dict(path_metadata["_shadow_physical_window"]))
            path_metadata["evidence_found"] = bool(matched)
            _merge_reader_metadata(reader_metadata, path_metadata)
        ambiguous = bool(active_context.identity_ambiguous and not active_context.registry_anchored)
        reader_metadata["evidence_found"] = bool(matched)
        reader_metadata["conclusive"] = bool(reader_metadata["coverage_complete"] and not ambiguous)
        if ambiguous:
            reader_metadata["evidence_status"] = "IDENTITY_AMBIGUOUS"
        elif reader_metadata.get("stop_reason") == "SOURCE_CHANGED":
            reader_metadata["evidence_status"] = "SOURCE_CHANGED"
        elif matched:
            reader_metadata["evidence_status"] = "EVIDENCE_FOUND"
        elif reader_metadata["coverage_complete"]:
            reader_metadata["evidence_status"] = "COMPLETE_NO_EVIDENCE"
        else:
            reader_metadata["evidence_status"] = "NOT_FOUND_IN_SCANNED_REGION"
        result = {
            "records": matched,
            "_reader_metadata": reader_metadata,
            "_identity_metadata": identity_resolution_metadata(active_context),
            "_evidence_correlated": True,
            "_correlation_context": active_context,
        }
        if capture_shadow:
            try:
                result["_shadow_index_capture"] = {
                    "component": component,
                    "context_before": context_before,
                    "context_after": copy.deepcopy(active_context),
                    "physical_windows": tuple(physical_windows),
                    "legacy_duration_ms": round(
                        (time.perf_counter() - shadow_legacy_started) * 1000.0, 6
                    ) if shadow_legacy_started is not None else 0.0,
                    "legacy_bytes_scanned": int(reader_metadata.get("bytes_scanned", 0) or 0),
                }
            except Exception:
                result.pop("_shadow_index_capture", None)
        return result

    return read


def build_default_sources(
    environ: Optional[Mapping[str, str]] = None,
    *,
    scan_cursor: Optional[str] = None,
    opened_at: Any = None,
    opened_epoch: Any = None,
    instance_id: Any = None,
    correlation_context: Optional[CorrelationContext] = None,
) -> Dict[str, Callable[[str], Dict[str, Any]]]:
    """Constroi leitores locais. Nao le arquivos ate a validacao ser solicitada."""
    configured_paths = default_source_paths(environ)
    decoded_cursor = _decode_scan_cursor(scan_cursor) if scan_cursor else None
    if decoded_cursor and not any(
        path.suffix.lower() == ".jsonl" and _cursor_targets_path(decoded_cursor, path)
        for paths in configured_paths.values()
        for path in paths
    ):
        raise ValueError("scan cursor belongs to an unconfigured source")
    context = correlation_context or new_correlation_context(
        "",
        opened_at=opened_at,
        opened_epoch=opened_epoch,
        instance_id=instance_id,
    )

    def reader_for(name: str, paths: tuple[Path, ...]) -> Callable[[str], Dict[str, Any]]:
        def read(trade_id: str) -> Dict[str, Any]:
            if context.trade_id != str(trade_id or "").strip():
                fresh = new_correlation_context(
                    trade_id,
                    opened_at=opened_at,
                    opened_epoch=opened_epoch,
                    instance_id=instance_id,
                )
                context.trade_id = fresh.trade_id
                context.trusted = fresh.trusted
                context.trusted_typed = fresh.trusted_typed
                context.profile = fresh.profile
                context.opened_epoch = None
                context.closed_epoch = None
                context.registry_anchored = False
                context.identity_ambiguous = False
                context.requested_opened_at = fresh.requested_opened_at
                context.requested_opened_epoch = fresh.requested_opened_epoch
                context.requested_instance_id = fresh.requested_instance_id
                context.registry_candidate_count = 0
                context.registry_candidates = []
                context.registry_candidates_truncated = False
                context.registry_selection_basis = None
            return _default_reader(name, paths, context, scan_cursor=scan_cursor)(trade_id)

        return read

    return {name: reader_for(name, paths) for name, paths in configured_paths.items()}


def _coerce_records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("records", "items", "events", "lifecycles"):
            if isinstance(value.get(key), list):
                head = {
                    k: v
                    for k, v in value.items()
                    if k not in {
                        key,
                        "_reader_metadata",
                        "_identity_metadata",
                        "_evidence_correlated",
                        "_correlation_context",
                        "_shadow_index_capture",
                    }
                }
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
    partial = bool(metadata.get("partial", False))
    coverage_limited = bool(metadata.get("coverage_limited", False))
    coverage_complete = bool(metadata.get("coverage_complete", not (partial or coverage_limited)))
    projected = {
        "lines_scanned": int(metadata.get("lines_scanned", 0) or 0),
        "valid_lines": int(metadata.get("valid_lines", 0) or 0),
        "invalid_lines": int(metadata.get("invalid_lines", 0) or 0),
        "partial": partial,
        "bytes_scanned": int(metadata.get("bytes_scanned", 0) or 0),
        "coverage_limited": coverage_limited,
        "files_read": int(metadata.get("files_read", 0) or 0),
        "evidence_found": bool(metadata.get("evidence_found", False)),
        "coverage_complete": coverage_complete,
        "conclusive": bool(metadata.get("conclusive", coverage_complete)),
        "records_examined": int(metadata.get("records_examined", metadata.get("valid_lines", 0)) or 0),
        "direction": str(metadata.get("direction") or "UNKNOWN"),
        "time_range_scanned": dict(metadata.get("time_range_scanned") or {"oldest": None, "newest": None}),
        "stop_reason": str(metadata.get("stop_reason") or "UNKNOWN"),
        "source_size_bytes": int(metadata.get("source_size_bytes", 0) or 0),
        "snapshot_eof": int(metadata.get("snapshot_eof", 0) or 0),
        "evidence_status": str(metadata.get("evidence_status") or (
            "NOT_FOUND_IN_SCANNED_REGION" if not coverage_complete else "COMPLETE_NO_EVIDENCE"
        )),
    }
    if metadata.get("next_scan_cursor"):
        projected["next_scan_cursor"] = str(metadata["next_scan_cursor"])
    return projected


def _parse_timestamp(value: Any) -> tuple[Optional[float], Optional[str]]:
    return _physical_parse_timestamp(value)


def _first_timestamp(record: Mapping[str, Any], preferred: Optional[str] = None) -> tuple[Optional[float], Optional[str]]:
    return _physical_first_timestamp(
        record,
        preferred,
        timestamp_keys=TIMESTAMP_KEYS,
    )


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


def _unavailable_source_coverage() -> Dict[str, Any]:
    return {
        "evidence_found": False,
        "coverage_complete": False,
        "partial": True,
        "conclusive": False,
        "bytes_scanned": 0,
        "records_examined": 0,
        "direction": "UNAVAILABLE",
        "time_range_scanned": {"oldest": None, "newest": None},
        "stop_reason": "SOURCE_UNAVAILABLE",
        "source_size_bytes": 0,
        "snapshot_eof": 0,
        "evidence_status": "COVERAGE_LIMITED",
    }


def _error_source_coverage() -> Dict[str, Any]:
    coverage = _unavailable_source_coverage()
    coverage.update({"direction": "ERROR", "stop_reason": "SOURCE_ERROR"})
    return coverage


def collect_evidence_bundle(
    trade_id: str,
    *,
    sources: Optional[Mapping[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    scan_cursor: Optional[str] = None,
    opened_at: Any = None,
    opened_epoch: Any = None,
    instance_id: Any = None,
    component_order: Iterable[str] = COMPONENTS,
    passthrough_components: Iterable[str] = (),
    record_coercer: Optional[Callable[[Any], list[Mapping[str, Any]]]] = None,
) -> EvidenceBundle:
    """Read and correlate source evidence exactly once for one request."""

    identity = str(trade_id or "").strip()
    active_logger = logger or LOGGER
    names = tuple(dict.fromkeys(str(name) for name in component_order))
    passthrough = frozenset(str(name) for name in passthrough_components)
    coerce_records = record_coercer or _coerce_records
    correlation = new_correlation_context(
        identity,
        opened_at=opened_at,
        opened_epoch=opened_epoch,
        instance_id=instance_id,
    )
    source_map = (
        dict(sources)
        if sources is not None
        else build_default_sources(
            scan_cursor=scan_cursor,
            opened_at=opened_at,
            opened_epoch=opened_epoch,
            instance_id=instance_id,
            correlation_context=correlation,
        )
    )
    records: Dict[str, list[Mapping[str, Any]]] = {}
    raw_sources: Dict[str, Any] = {}
    components: Dict[str, Dict[str, Any]] = {}
    source_coverage: Dict[str, Dict[str, Any]] = {}
    warnings: list[Dict[str, Any]] = []
    errors: list[Dict[str, Any]] = []

    for name in names:
        source = source_map.get(name)
        if source is None:
            records[name] = []
            components[name] = {"status": "UNAVAILABLE", "records": 0}
            source_coverage[name] = _unavailable_source_coverage()
            continue
        try:
            value = source(identity) if callable(source) else source
            raw_sources[name] = value
            source_context = value.get("_correlation_context") if isinstance(value, Mapping) else None
            already_correlated = bool(
                isinstance(value, Mapping)
                and value.get("_evidence_correlated") is True
                and isinstance(source_context, CorrelationContext)
            )
            if already_correlated:
                # Default readers share this request-local context and already
                # applied rejection-first identity correlation while streaming.
                correlation = source_context
                rows = coerce_records(value)
            else:
                apply_identity_resolution_metadata(correlation, value)
                candidates = coerce_records(value)
                rows = (
                    candidates
                    if name in passthrough
                    else correlate_source_records(name, candidates, correlation)
                )

            reader_metadata = _reader_metadata(value)
            if reader_metadata:
                reader_metadata["evidence_found"] = bool(
                    rows or reader_metadata.get("evidence_found", False)
                )
                if rows and reader_metadata.get("evidence_status") not in {
                    "SOURCE_CHANGED",
                    "IDENTITY_AMBIGUOUS",
                }:
                    reader_metadata["evidence_status"] = "EVIDENCE_FOUND"
            records[name] = rows
            fully_corrupt = bool(
                reader_metadata.get("files_read", 0) > 0
                and reader_metadata.get("lines_scanned", 0) > 0
                and reader_metadata.get("valid_lines", 0) == 0
                and reader_metadata.get("invalid_lines", 0) > 0
            )
            status = "AVAILABLE" if rows else ("DEGRADED" if fully_corrupt else "NO_EVIDENCE")
            components[name] = {"status": status, "records": len(rows), **reader_metadata}
            if name == "registry" and correlation.registry_candidate_count:
                components[name]["identity_ambiguous"] = bool(
                    correlation.identity_ambiguous and not correlation.registry_anchored
                )
                components[name]["candidate_count"] = correlation.registry_candidate_count
            source_coverage[name] = {
                "evidence_found": bool(reader_metadata.get("evidence_found", bool(rows))),
                "coverage_complete": bool(reader_metadata.get("coverage_complete", True)),
                "partial": bool(reader_metadata.get("partial", False)),
                "conclusive": bool(reader_metadata.get("conclusive", True)),
                "bytes_scanned": int(reader_metadata.get("bytes_scanned", 0) or 0),
                "records_examined": int(reader_metadata.get("records_examined", len(rows)) or 0),
                "direction": reader_metadata.get("direction", "IN_MEMORY"),
                "time_range_scanned": dict(
                    reader_metadata.get("time_range_scanned")
                    or {"oldest": None, "newest": None}
                ),
                "stop_reason": reader_metadata.get("stop_reason", "IN_MEMORY_COMPLETE"),
                "source_size_bytes": int(reader_metadata.get("source_size_bytes", 0) or 0),
                "snapshot_eof": int(reader_metadata.get("snapshot_eof", 0) or 0),
                "evidence_status": reader_metadata.get(
                    "evidence_status",
                    "EVIDENCE_FOUND" if rows else "COMPLETE_NO_EVIDENCE",
                ),
            }
            if reader_metadata.get("next_scan_cursor"):
                source_coverage[name]["next_scan_cursor"] = reader_metadata["next_scan_cursor"]
            if reader_metadata.get("invalid_lines", 0) > 0:
                warnings.append({
                    "component": name,
                    "code": "CORRUPT_JSONL_LINES_SKIPPED",
                    "count": reader_metadata["invalid_lines"],
                })
            _structured_log(
                active_logger,
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
            raw_sources[name] = None
            components[name] = {
                "status": "ERROR",
                "records": 0,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            }
            source_coverage[name] = _error_source_coverage()
            errors.append({
                "component": name,
                "error_type": type(exc).__name__,
                "message": str(exc)[:300],
            })
            _structured_log(
                active_logger,
                "warning",
                "TRADE_TIMELINE_SOURCE_ERROR",
                trade_id=identity,
                component=name,
                error_type=type(exc).__name__,
            )

    events: list[Dict[str, Any]] = []
    for component in COMPONENTS:
        for record in records.get(component, ()):
            events.extend(_events_from_record(component, record))
    events = _deduplicate_extracted(events)
    events.sort(
        key=lambda item: (
            item.get("epoch") is None,
            item.get("epoch") or 0.0,
            EVENT_ORDER.index(item["event"]) if item["event"] in EVENT_ORDER else 999,
        )
    )
    matched_identifiers = {
        key: tuple(sorted(values))
        for key, values in sorted(correlation.trusted_typed.items())
        if values
    }
    source_fingerprints = {
        name: {
            "source_size_bytes": int(detail.get("source_size_bytes", 0) or 0),
            "snapshot_eof": int(detail.get("snapshot_eof", 0) or 0),
        }
        for name, detail in source_coverage.items()
    }
    legacy_bundle = EvidenceBundle(
        trade_id=identity,
        target_identity=target_identity_from_context(correlation),
        registry_resolution=identity_resolution_metadata(correlation),
        records={name: tuple(rows) for name, rows in records.items()},
        raw_sources=dict(raw_sources),
        source_coverage={name: dict(detail) for name, detail in source_coverage.items()},
        component_status={name: dict(detail) for name, detail in components.items()},
        events=tuple(events),
        matched_identifiers=matched_identifiers,
        source_fingerprints=source_fingerprints,
        warnings=tuple(warnings),
        errors=tuple(errors),
        correlation=correlation,
    )
    shadow_requested = bool(
        str(os.environ.get("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "")).strip().lower()
        in {"1", "true", "yes", "on"}
        and str(os.environ.get("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", "")).strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if shadow_requested:
        try:
            from trade_evidence_identity_offset_shadow_compare_v1 import observe_evidence_bundle

            observe_evidence_bundle(legacy_bundle, logger=active_logger)
        except Exception as exc:
            # Final isolation barrier: shadow diagnostics never alter, replace,
            # or invalidate the already-complete authoritative legacy bundle.
            _structured_log(
                active_logger,
                "warning",
                "TRADE_EVIDENCE_INDEX_SHADOW_EXCEPTION_ISOLATED",
                trade_id_masked=hashlib.sha256(
                    identity.encode("utf-8", errors="replace")
                ).hexdigest()[:12],
                error_type=type(exc).__name__,
            )
    return legacy_bundle


class TradeTimelineValidator:
    """Validador read-only. Excecoes de fontes sao convertidas em evidencia."""

    def __init__(
        self,
        sources: Optional[Mapping[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        scan_cursor: Optional[str] = None,
        opened_at: Any = None,
        opened_epoch: Any = None,
        instance_id: Any = None,
    ):
        self.opened_at = opened_at
        self.opened_epoch = opened_epoch
        self.instance_id = instance_id
        self.sources = dict(sources) if sources is not None else None
        self.scan_cursor = scan_cursor
        self.logger = logger or LOGGER

    def validate(
        self,
        trade_id: str,
        *,
        evidence_bundle: Optional[EvidenceBundle] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        identity = str(trade_id or "").strip()
        _structured_log(self.logger, "info", "TRADE_TIMELINE_VALIDATION_BEGIN", trade_id=identity)
        bundle = evidence_bundle or collect_evidence_bundle(
            identity,
            sources=self.sources,
            logger=self.logger,
            scan_cursor=self.scan_cursor,
            opened_at=self.opened_at,
            opened_epoch=self.opened_epoch,
            instance_id=self.instance_id,
        )
        if bundle.trade_id != identity:
            raise ValueError("evidence bundle belongs to another trade")

        components = {
            name: dict(bundle.component_status.get(name) or {"status": "UNAVAILABLE", "records": 0})
            for name in COMPONENTS
        }
        records = {name: list(bundle.records.get(name, ())) for name in COMPONENTS}
        source_coverage = {
            name: dict(bundle.source_coverage.get(name) or _unavailable_source_coverage())
            for name in COMPONENTS
        }
        errors = [
            dict(item)
            for item in bundle.errors
            if item.get("component") in COMPONENTS
        ]
        warnings = [
            dict(item)
            for item in bundle.warnings
            if item.get("component") in COMPONENTS
        ]
        correlation = bundle.correlation

        if not identity:
            errors.append({"component": "validator", "error_type": "ValueError", "message": "trade_id is required"})

        events = [dict(item) for item in bundle.events]

        present = {item["event"] for item in events}
        missing = [name for name in REQUIRED_EVENTS if name not in present]
        duplicates = _duplicates(events)
        chronology = _chronology(events)
        facts = {name: _facts(rows, name) for name, rows in records.items()}
        divergences = _compare("registry", "broker", facts) + _compare("lifecycle", "shadow_runtime", facts)
        timeline_absent = components["timeline"]["status"] != "AVAILABLE"
        validation_errors = bool(errors or missing or duplicates or divergences or not chronology["ordered"] or timeline_absent or not identity)
        result = "FAIL" if validation_errors else "PASS"

        ranges = [
            detail["time_range_scanned"]
            for detail in source_coverage.values()
            if isinstance(detail.get("time_range_scanned"), Mapping)
        ]
        oldest = [item.get("oldest") for item in ranges if item.get("oldest")]
        newest = [item.get("newest") for item in ranges if item.get("newest")]
        coverage_complete = all(
            bool(detail.get("coverage_complete", False))
            for detail in source_coverage.values()
        )
        partial = any(bool(detail.get("partial", False)) for detail in source_coverage.values())
        evidence_found = any(bool(detail.get("evidence_found", False)) for detail in source_coverage.values())
        identity_ambiguous = bool(correlation.identity_ambiguous and not correlation.registry_anchored)
        conclusive = bool(coverage_complete and not identity_ambiguous and not errors)
        reasons = {str(detail.get("stop_reason") or "UNKNOWN") for detail in source_coverage.values()}
        if "SOURCE_CHANGED" in reasons:
            stop_reason = "SOURCE_CHANGED"
        elif partial:
            stop_reason = "COVERAGE_LIMITED"
        elif len(reasons) == 1:
            stop_reason = next(iter(reasons))
        else:
            stop_reason = "MULTIPLE_COMPLETE_SOURCES"
        if identity_ambiguous:
            evidence_status = "IDENTITY_AMBIGUOUS"
        elif "SOURCE_CHANGED" in reasons:
            evidence_status = "SOURCE_CHANGED"
        elif evidence_found:
            evidence_status = "EVIDENCE_FOUND"
        elif coverage_complete:
            evidence_status = "COMPLETE_NO_EVIDENCE"
        else:
            evidence_status = "NOT_FOUND_IN_SCANNED_REGION"
        aggregate_coverage: Dict[str, Any] = {
            "evidence_found": evidence_found,
            "coverage_complete": coverage_complete,
            "partial": partial,
            "conclusive": conclusive,
            "bytes_scanned": sum(int(detail.get("bytes_scanned", 0) or 0) for detail in source_coverage.values()),
            "records_examined": sum(int(detail.get("records_examined", 0) or 0) for detail in source_coverage.values()),
            "direction": "REVERSE" if any(detail.get("direction") == "REVERSE" for detail in source_coverage.values()) else "IN_MEMORY",
            "time_range_scanned": {
                "oldest": min(oldest) if oldest else None,
                "newest": max(newest) if newest else None,
            },
            "stop_reason": stop_reason,
            "source_size_bytes": sum(int(detail.get("source_size_bytes", 0) or 0) for detail in source_coverage.values()),
            "snapshot_eof": sum(int(detail.get("snapshot_eof", 0) or 0) for detail in source_coverage.values()),
        }
        next_cursors = {
            name: detail["next_scan_cursor"]
            for name, detail in source_coverage.items()
            if detail.get("next_scan_cursor")
        }
        if next_cursors:
            aggregate_coverage["next_scan_cursors"] = next_cursors

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
            "coverage": {"aggregate": aggregate_coverage, "sources": source_coverage},
            "conclusive": conclusive,
            "evidence_status": evidence_status,
            "identity": {
                "registry_anchored": correlation.registry_anchored,
                "ambiguous": identity_ambiguous,
                "selection_basis": correlation.registry_selection_basis,
                "candidate_count": correlation.registry_candidate_count,
                "candidates": _json_safe(correlation.registry_candidates),
                "candidates_truncated": correlation.registry_candidates_truncated,
            },
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


def validate_trade_timeline(
    trade_id: str,
    *,
    sources: Optional[Mapping[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    scan_cursor: Optional[str] = None,
    opened_at: Any = None,
    opened_epoch: Any = None,
    instance_id: Any = None,
    evidence_bundle: Optional[EvidenceBundle] = None,
) -> Dict[str, Any]:
    """API publica fail-open para validacao de um trade."""
    try:
        return TradeTimelineValidator(
            sources=sources,
            logger=logger,
            scan_cursor=scan_cursor,
            opened_at=opened_at,
            opened_epoch=opened_epoch,
            instance_id=instance_id,
        ).validate(trade_id, evidence_bundle=evidence_bundle)
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
            "coverage": {
                "aggregate": {
                    "evidence_found": False,
                    "coverage_complete": False,
                    "partial": True,
                    "conclusive": False,
                    "bytes_scanned": 0,
                    "records_examined": 0,
                    "direction": "ERROR",
                    "time_range_scanned": {"oldest": None, "newest": None},
                    "stop_reason": "VALIDATOR_ERROR",
                    "source_size_bytes": 0,
                    "snapshot_eof": 0,
                },
                "sources": {},
            },
            "conclusive": False,
            "evidence_status": "COVERAGE_LIMITED",
            "errors": [{"component": "validator", "error_type": type(exc).__name__, "message": str(exc)[:300]}],
        }


__all__ = [
    "COMPONENTS",
    "EVENT_ORDER",
    "REQUIRED_EVENTS",
    "CorrelationContext",
    "EvidenceBundle",
    "TargetIdentity",
    "TradeTimelineValidator",
    "apply_identity_resolution_metadata",
    "build_default_sources",
    "collect_evidence_bundle",
    "correlate_source_records",
    "default_source_paths",
    "identity_resolution_metadata",
    "new_correlation_context",
    "target_identity_from_context",
    "validate_trade_timeline",
]
