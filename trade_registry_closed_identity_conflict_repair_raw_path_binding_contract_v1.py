"""Dormant raw-path binding contract for CLOSED conflict repair proposals.

The contract consumes only injected, synthetic in-memory documents.  It proves
that planner proposals, raw collection locators, legacy identity fingerprints,
exact source paths, raw JSON types and source values all refer to the same
immutable preimage.  It never translates values and can never authorize an
apply, persistence, runtime integration or trading action.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PATH_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-PATH-BINDING-CONTRACT-V1"
)

_SNAPSHOT_VERSION = "SYNTHETIC_RAW_TRADE_REGISTRY_SNAPSHOT_V1"
_INVENTORY_VERSION = "SYNTHETIC_RAW_PATH_BINDING_INVENTORY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TRANSIENT_METADATA_FIELDS = frozenset(
    {"closed_history_sources", "closed_identity_merge"}
)
_LEGACY_ALIAS_FAMILIES = {
    "trade_id": ("trade_id",),
    "registry_mode": ("registry_mode",),
    "execution_mode": ("execution_mode",),
    "opened_at": ("opened_at", "open_timestamp", "created_at", "entry_timestamp"),
    "closed_at": ("closed_at", "close_timestamp", "exit_timestamp"),
    "entry": ("entry", "entry_price", "filled_entry_price"),
    "qty": ("qty", "initial_qty", "quantity", "quantity_opened"),
    "bot": ("bot",),
    "setup": ("setup", "signal_type", "setup_label"),
    "symbol": ("symbol", "symbol_clean"),
    "side": ("side", "direction"),
    "status": ("status",),
}
_FINANCIAL_ALIAS_FAMILIES = {
    "close_reason": ("close_reason", "exit_reason"),
    "pnl_r": ("pnl_r", "result_r", "r_multiple"),
}
_FINANCIAL_CONTAINERS = (
    (),
    ("metadata",),
    ("outcome",),
    ("metadata", "outcome"),
    ("raw",),
    ("source_event",),
)
_BINDING_KEYS = {
    "proposal_ordinal",
    "proposal_sha256",
    "proposal_type",
    "registry_index",
    "registry_collection_key",
    "collection_shape",
    "record_fingerprint",
    "legacy_identity_fingerprint",
    "raw_record_sha256",
    "conflict_sha256",
    "evidence_sha256",
    "path_bindings",
    "binding_sha256",
}
_PATH_BINDING_KEYS = {
    "canonical_field",
    "alias",
    "path",
    "raw_type",
    "raw_value",
    "raw_value_sha256",
    "normalized_value",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _json_copy_preserving_object_order(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def raw_registry_document_sha256_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    return _stable_sha256(document)


def raw_closed_collection_locator_sha256_v1(document: Mapping[str, Any]) -> str:
    """Bind list positions or the original object-key enumeration order."""

    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    closed = document.get("closed_trades")
    if isinstance(closed, list):
        locator = {"collection_shape": "list", "locators": list(range(len(closed)))}
    elif isinstance(closed, Mapping):
        locator = {"collection_shape": "dict", "locators": list(closed)}
    else:
        raise TypeError("closed_trades must be a list or mapping")
    return _stable_sha256(locator)


def raw_registry_snapshot_envelope_sha256_v1(snapshot: Mapping[str, Any]) -> str:
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a mapping")
    return _stable_sha256(
        {key: value for key, value in snapshot.items() if key != "snapshot_envelope_sha256"}
    )


def raw_path_binding_sha256_v1(binding: Mapping[str, Any]) -> str:
    if not isinstance(binding, Mapping):
        raise TypeError("binding must be a mapping")
    return _stable_sha256(
        {key: value for key, value in binding.items() if key != "binding_sha256"}
    )


def raw_path_binding_inventory_sha256_v1(inventory: Mapping[str, Any]) -> str:
    if not isinstance(inventory, Mapping):
        raise TypeError("inventory must be a mapping")
    return _stable_sha256(
        {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    )


def repair_plan_sha256_v1(plan: Mapping[str, Any]) -> str:
    if not isinstance(plan, Mapping):
        raise TypeError("plan must be a mapping")
    return _stable_sha256({key: value for key, value in plan.items() if key != "plan_sha256"})


def _legacy_identity_document(record: Mapping[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(dict(record))
    document.pop("closed_history_identity_merge", None)
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        metadata = copy.deepcopy(metadata)
        for field in _TRANSIENT_METADATA_FIELDS:
            metadata.pop(field, None)
        if metadata:
            document["metadata"] = metadata
        else:
            document.pop("metadata", None)
    return document


def legacy_raw_closed_trade_identity_fingerprint_v1(record: Mapping[str, Any]) -> str:
    """Mirror the legacy identity-document digest without importing runtime."""

    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")
    return _stable_sha256(_legacy_identity_document(record))


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unsupported"


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _decimal_text(value: Any) -> str:
    try:
        if value in (None, "") or isinstance(value, bool):
            return ""
        number = Decimal(str(value).replace(",", ".").strip())
        if not number.is_finite():
            return ""
        if number == 0:
            return "0"
        return format(number.normalize(), "f")
    except (InvalidOperation, ValueError, TypeError):
        return ""


def _timestamp_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat()
    except (TypeError, ValueError):
        return text


def _normalize_legacy(field: str, value: Any) -> str:
    if field in {"opened_at", "closed_at"}:
        return _timestamp_text(value)
    if field in {"entry", "qty"}:
        return _decimal_text(value)
    text = str(value or "").strip()
    if field == "setup":
        return "".join(text.upper().split())
    if field == "symbol":
        return text.upper().replace("/", "").replace(":USDT", "").replace("-", "")
    if field == "side":
        side = text.upper()
        return {"BUY": "LONG", "SELL": "SHORT"}.get(side, side)
    if field in {"registry_mode", "execution_mode", "bot", "status"}:
        return text.upper()
    return text


def _normalize_financial(field: str, value: Any) -> str:
    if field == "close_reason":
        return str(value or "").strip().upper()
    if field == "pnl_r":
        return _decimal_text(value)
    return ""


def _read_source_path(record: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    parts = path.split(".")
    if len(parts) < 2 or parts[0] != "trade" or any(not part for part in parts):
        return False, None
    current: Any = record
    for part in parts[1:]:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _discovered_legacy_paths(record: Mapping[str, Any], field: str) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for alias in _LEGACY_ALIAS_FAMILIES.get(field, ()):
        if _nonempty(record.get(alias)):
            discovered[f"trade.{alias}"] = alias
        metadata = record.get("metadata")
        if isinstance(metadata, Mapping) and _nonempty(metadata.get(alias)):
            discovered[f"trade.metadata.{alias}"] = alias
    return discovered


def _discovered_financial_paths(
    record: Mapping[str, Any], canonical_field: str
) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for container_parts in _FINANCIAL_CONTAINERS:
        container: Any = record
        for part in container_parts:
            if not isinstance(container, Mapping):
                container = None
                break
            container = container.get(part)
        if not isinstance(container, Mapping):
            continue
        for alias in _FINANCIAL_ALIAS_FAMILIES[canonical_field]:
            if _nonempty(container.get(alias)):
                path = ".".join(("trade", *container_parts, alias))
                discovered[path] = alias
    return discovered


def _locate_raw_record(
    document: Mapping[str, Any], binding: Mapping[str, Any], reasons: list[str]
) -> Mapping[str, Any] | None:
    closed = document.get("closed_trades")
    index = binding.get("registry_index")
    key = binding.get("registry_collection_key")
    shape = binding.get("collection_shape")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        reasons.append("REGISTRY_INDEX_INVALID")
        return None
    if isinstance(closed, list):
        if shape != "list" or key is not None or index >= len(closed):
            reasons.append("LIST_COLLECTION_LOCATOR_MISMATCH")
            return None
        record = closed[index]
    elif isinstance(closed, Mapping):
        keys = list(closed)
        if (
            shape != "dict"
            or not isinstance(key, str)
            or not key
            or index >= len(keys)
            or keys[index] != key
        ):
            reasons.append("DICT_COLLECTION_LOCATOR_MISMATCH")
            return None
        record = closed.get(key)
    else:
        reasons.append("RAW_CLOSED_TRADES_COLLECTION_INVALID")
        return None
    if not isinstance(record, Mapping):
        reasons.append("RAW_CLOSED_TRADE_RECORD_INVALID")
        return None
    return record


def _validate_path_descriptor(
    descriptor: Mapping[str, Any],
    record: Mapping[str, Any],
    reasons: list[str],
) -> tuple[str, str, str] | None:
    if set(descriptor) != _PATH_BINDING_KEYS:
        reasons.append("RAW_PATH_DESCRIPTOR_SCHEMA_INVALID")
        return None
    canonical_field = str(descriptor.get("canonical_field") or "").strip()
    alias = str(descriptor.get("alias") or "").strip()
    path = str(descriptor.get("path") or "").strip()
    exists, raw_value = _read_source_path(record, path)
    if not exists:
        reasons.append("RAW_PATH_NOT_FOUND")
        return None
    if path.split(".")[-1] != alias:
        reasons.append("RAW_PATH_ALIAS_MISMATCH")
    if descriptor.get("raw_type") != _json_type(raw_value):
        reasons.append("RAW_PATH_TYPE_MISMATCH")
    try:
        actual_value_sha = _stable_sha256(raw_value)
        supplied_value_sha = _valid_sha256(descriptor.get("raw_value_sha256"))
        copied_value_sha = _stable_sha256(descriptor.get("raw_value"))
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_PATH_VALUE_NOT_CANONICALIZABLE")
        return None
    if not (
        supplied_value_sha
        and hmac.compare_digest(supplied_value_sha, actual_value_sha)
        and hmac.compare_digest(copied_value_sha, actual_value_sha)
    ):
        reasons.append("RAW_PATH_VALUE_SHA256_MISMATCH")
    return canonical_field, alias, path


def _validate_legacy_proposal_paths(
    proposal: Mapping[str, Any],
    record: Mapping[str, Any],
    descriptors: list[Mapping[str, Any]],
    reasons: list[str],
) -> None:
    field = str(proposal.get("field") or "").strip()
    if field not in _LEGACY_ALIAS_FAMILIES:
        reasons.append("LEGACY_FIELD_INVALID")
        return
    expected_aliases = proposal.get("expected_current_aliases")
    candidates = proposal.get("expected_current_normalized_values")
    selected = proposal.get("selected_normalized_value")
    updates = proposal.get("canonical_alias_updates")
    if not isinstance(expected_aliases, list) or len(expected_aliases) < 2:
        reasons.append("LEGACY_EXPECTED_ALIASES_INVALID")
        expected_aliases = []
    if not isinstance(candidates, list) or len(candidates) < 2:
        reasons.append("LEGACY_EXPECTED_CANDIDATES_INVALID")
        candidates = []
    normalized_candidates = sorted({str(value) for value in candidates})
    if str(selected) not in normalized_candidates:
        reasons.append("LEGACY_SELECTED_VALUE_INVALID")
    if not isinstance(updates, Mapping) or set(updates) != set(expected_aliases):
        reasons.append("LEGACY_CANONICAL_UPDATES_INVALID")
    elif any(str(value) != str(selected) for value in updates.values()):
        reasons.append("LEGACY_CANONICAL_UPDATE_VALUE_MISMATCH")

    discovered = _discovered_legacy_paths(record, field)
    paths = {str(item.get("path") or "") for item in descriptors}
    if paths != set(discovered) or paths != set(expected_aliases):
        reasons.append("LEGACY_RAW_PATH_COVERAGE_MISMATCH")
    descriptor_values: set[str] = set()
    for descriptor in descriptors:
        validated = _validate_path_descriptor(descriptor, record, reasons)
        if validated is None:
            continue
        canonical_field, alias, path = validated
        if canonical_field != field or discovered.get(path) != alias:
            reasons.append("LEGACY_RAW_PATH_FIELD_OR_ALIAS_MISMATCH")
            continue
        exists, raw_value = _read_source_path(record, path)
        normalized = _normalize_legacy(field, raw_value) if exists else ""
        if descriptor.get("normalized_value") != normalized:
            reasons.append("LEGACY_NORMALIZED_VALUE_MISMATCH")
        if normalized:
            descriptor_values.add(normalized)
    if sorted(descriptor_values) != normalized_candidates:
        reasons.append("LEGACY_NORMALIZED_CANDIDATE_COVERAGE_MISMATCH")


def _validate_financial_proposal_paths(
    proposal: Mapping[str, Any],
    record: Mapping[str, Any],
    descriptors: list[Mapping[str, Any]],
    reasons: list[str],
) -> None:
    trade_id = str(proposal.get("trade_id") or "").strip()
    if not trade_id or trade_id != str(record.get("trade_id") or "").strip():
        reasons.append("FINANCIAL_TRADE_ID_MISMATCH")
    strong_identity = proposal.get("strong_identity")
    if not isinstance(strong_identity, Mapping) or not strong_identity:
        reasons.append("FINANCIAL_STRONG_IDENTITY_REQUIRED")
        strong_identity = {}
    if set(strong_identity) - {"lifecycle_id", "client_order_id", "order_id"}:
        reasons.append("FINANCIAL_STRONG_IDENTITY_FIELD_INVALID")
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    for field, selected in strong_identity.items():
        normalized_selected = str(selected or "").strip()
        if field == "client_order_id":
            normalized_selected = normalized_selected.upper()
        candidates = set()
        for source in (record, metadata):
            raw = source.get(field)
            if not _nonempty(raw):
                continue
            normalized = str(raw).strip()
            if field == "client_order_id":
                normalized = normalized.upper()
            candidates.add(normalized)
        if len(candidates) != 1 or normalized_selected not in candidates:
            reasons.append("FINANCIAL_STRONG_IDENTITY_MISMATCH")

    expected = proposal.get("expected_current_candidates")
    updates = proposal.get("canonical_updates")
    if not isinstance(expected, Mapping) or set(expected) != set(_FINANCIAL_ALIAS_FAMILIES):
        reasons.append("FINANCIAL_EXPECTED_CANDIDATES_INVALID")
        expected = {}
    if not isinstance(updates, Mapping) or set(updates) != set(_FINANCIAL_ALIAS_FAMILIES):
        reasons.append("FINANCIAL_CANONICAL_UPDATES_INVALID")
        updates = {}
    grouped: dict[str, list[Mapping[str, Any]]] = {
        field: [] for field in _FINANCIAL_ALIAS_FAMILIES
    }
    for descriptor in descriptors:
        canonical_field = str(descriptor.get("canonical_field") or "")
        if canonical_field not in grouped:
            reasons.append("FINANCIAL_RAW_PATH_FIELD_INVALID")
            continue
        grouped[canonical_field].append(descriptor)
    for field, field_descriptors in grouped.items():
        discovered = _discovered_financial_paths(record, field)
        paths = {str(item.get("path") or "") for item in field_descriptors}
        if paths != set(discovered) or len(paths) < 2:
            reasons.append("FINANCIAL_RAW_PATH_COVERAGE_MISMATCH")
        descriptor_values: set[str] = set()
        for descriptor in field_descriptors:
            validated = _validate_path_descriptor(descriptor, record, reasons)
            if validated is None:
                continue
            canonical_field, alias, path = validated
            if canonical_field != field or discovered.get(path) != alias:
                reasons.append("FINANCIAL_RAW_PATH_FIELD_OR_ALIAS_MISMATCH")
                continue
            exists, raw_value = _read_source_path(record, path)
            normalized = _normalize_financial(field, raw_value) if exists else ""
            if descriptor.get("normalized_value") != normalized:
                reasons.append("FINANCIAL_NORMALIZED_VALUE_MISMATCH")
            if normalized:
                descriptor_values.add(normalized)
        candidate_values = expected.get(field)
        if not isinstance(candidate_values, list) or len(candidate_values) < 2:
            reasons.append("FINANCIAL_FIELD_CANDIDATES_INVALID")
            normalized_candidates: set[str] = set()
        else:
            normalized_candidates = {
                _normalize_financial(field, value) for value in candidate_values
            }
            normalized_candidates.discard("")
        if descriptor_values != normalized_candidates or len(normalized_candidates) < 2:
            reasons.append("FINANCIAL_NORMALIZED_CANDIDATE_COVERAGE_MISMATCH")
        selected = _normalize_financial(field, updates.get(field))
        if selected not in normalized_candidates:
            reasons.append("FINANCIAL_CANONICAL_VALUE_NOT_A_CANDIDATE")


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "binding_verification_allowed": False,
        "bindings_valid": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "status": "CLOSED_IDENTITY_CONFLICT_RAW_PATH_BINDING_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PATH_BINDING_CONTRACT_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "read_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "persistence_allowed": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "translation_request": None,
    }


def bind_closed_identity_conflict_raw_paths_offline_v1(
    plan: Mapping[str, Any],
    raw_registry_snapshot: Mapping[str, Any],
    raw_path_inventory: Mapping[str, Any],
    *,
    max_bindings: int = 152,
) -> dict[str, Any]:
    """Validate path provenance and emit an inert, non-translatable request."""

    base = _base()
    reasons: list[str] = base["reasons"]
    if not all(
        isinstance(value, Mapping)
        for value in (plan, raw_registry_snapshot, raw_path_inventory)
    ):
        reasons.append("RAW_PATH_BINDING_MAPPING_INPUTS_REQUIRED")
        return base
    if not isinstance(max_bindings, int) or isinstance(max_bindings, bool) or max_bindings <= 0:
        reasons.append("RAW_PATH_BINDING_LIMIT_INVALID")
        return base
    try:
        plan_copy = _json_copy_preserving_object_order(plan)
        snapshot_copy = _json_copy_preserving_object_order(raw_registry_snapshot)
        inventory_copy = _json_copy_preserving_object_order(raw_path_inventory)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_PATH_BINDING_INPUT_NOT_CANONICALIZABLE")
        return base

    supplied_plan_sha = _valid_sha256(plan_copy.get("plan_sha256"))
    computed_plan_sha = repair_plan_sha256_v1(plan_copy)
    if not supplied_plan_sha or not hmac.compare_digest(supplied_plan_sha, computed_plan_sha):
        reasons.append("PLAN_SHA256_MISMATCH")
    proposals = plan_copy.get("proposals")
    if (
        plan_copy.get("offline_only") is not True
        or plan_copy.get("synthetic_only") is not True
        or not isinstance(proposals, list)
        or not proposals
        or len(proposals) > max_bindings
        or plan_copy.get("proposal_count") != len(proposals)
        or any(not isinstance(item, Mapping) for item in proposals)
    ):
        reasons.append("PLAN_ENVELOPE_INVALID")
        proposals = []

    document = snapshot_copy.get("raw_registry_document")
    supplied_document_sha = _valid_sha256(
        snapshot_copy.get("raw_registry_document_sha256")
    )
    supplied_snapshot_sha = _valid_sha256(snapshot_copy.get("snapshot_envelope_sha256"))
    supplied_locator_sha = _valid_sha256(
        snapshot_copy.get("closed_collection_locator_sha256")
    )
    if (
        snapshot_copy.get("snapshot_version") != _SNAPSHOT_VERSION
        or snapshot_copy.get("synthetic_only") is not True
        or snapshot_copy.get("offline_only") is not True
        or snapshot_copy.get("source_kind") != "INJECTED_SYNTHETIC_MEMORY"
        or not isinstance(document, Mapping)
        or "open_trades" not in document
        or "closed_trades" not in document
    ):
        reasons.append("RAW_REGISTRY_SNAPSHOT_ENVELOPE_INVALID")
        document = {}
    try:
        computed_document_sha = raw_registry_document_sha256_v1(document)
        computed_locator_sha = raw_closed_collection_locator_sha256_v1(document)
        computed_snapshot_sha = raw_registry_snapshot_envelope_sha256_v1(snapshot_copy)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_REGISTRY_SNAPSHOT_NOT_CANONICALIZABLE")
        computed_document_sha = ""
        computed_locator_sha = ""
        computed_snapshot_sha = ""
    if not (
        supplied_document_sha
        and hmac.compare_digest(supplied_document_sha, computed_document_sha)
    ):
        reasons.append("RAW_REGISTRY_DOCUMENT_SHA256_MISMATCH")
    if not supplied_snapshot_sha or not hmac.compare_digest(
        supplied_snapshot_sha, computed_snapshot_sha
    ):
        reasons.append("RAW_REGISTRY_SNAPSHOT_ENVELOPE_SHA256_MISMATCH")
    if not supplied_locator_sha or not hmac.compare_digest(
        supplied_locator_sha, computed_locator_sha
    ):
        reasons.append("RAW_CLOSED_COLLECTION_LOCATOR_SHA256_MISMATCH")

    supplied_inventory_sha = _valid_sha256(inventory_copy.get("inventory_sha256"))
    try:
        computed_inventory_sha = raw_path_binding_inventory_sha256_v1(inventory_copy)
    except (TypeError, ValueError, OverflowError):
        computed_inventory_sha = ""
    bindings = inventory_copy.get("bindings")
    if (
        inventory_copy.get("inventory_version") != _INVENTORY_VERSION
        or inventory_copy.get("synthetic_only") is not True
        or inventory_copy.get("offline_only") is not True
        or inventory_copy.get("plan_sha256") != supplied_plan_sha
        or inventory_copy.get("raw_registry_document_sha256") != supplied_document_sha
        or not isinstance(bindings, list)
        or len(bindings) != len(proposals)
        or inventory_copy.get("binding_count") != len(bindings)
        or any(not isinstance(item, Mapping) for item in bindings)
    ):
        reasons.append("RAW_PATH_INVENTORY_ENVELOPE_INVALID")
        bindings = []
    if not supplied_inventory_sha or not hmac.compare_digest(
        supplied_inventory_sha, computed_inventory_sha
    ):
        reasons.append("RAW_PATH_INVENTORY_SHA256_MISMATCH")

    validated_bindings: list[dict[str, Any]] = []
    if len(bindings) == len(proposals):
        for ordinal, (proposal, binding) in enumerate(zip(proposals, bindings, strict=True)):
            if set(binding) != _BINDING_KEYS:
                reasons.append("RAW_RECORD_BINDING_SCHEMA_INVALID")
                continue
            supplied_binding_sha = _valid_sha256(binding.get("binding_sha256"))
            computed_binding_sha = raw_path_binding_sha256_v1(binding)
            if not supplied_binding_sha or not hmac.compare_digest(
                supplied_binding_sha, computed_binding_sha
            ):
                reasons.append("RAW_RECORD_BINDING_SHA256_MISMATCH")
            proposal_sha = _stable_sha256(proposal)
            proposal_type = str(proposal.get("proposal_type") or "")
            if (
                binding.get("proposal_ordinal") != ordinal
                or binding.get("proposal_sha256") != proposal_sha
                or binding.get("proposal_type") != proposal_type
                or binding.get("registry_index") != proposal.get("registry_index")
                or binding.get("record_fingerprint") != proposal.get("record_fingerprint")
                or binding.get("conflict_sha256") != proposal.get("conflict_sha256")
                or binding.get("evidence_sha256") != proposal.get("evidence_sha256")
            ):
                reasons.append("RAW_RECORD_BINDING_PROPOSAL_MISMATCH")
            if not _valid_sha256(proposal.get("conflict_sha256")):
                reasons.append("PROPOSAL_CONFLICT_SHA256_INVALID")
            if not _valid_sha256(proposal.get("evidence_sha256")):
                reasons.append("PROPOSAL_EVIDENCE_SHA256_INVALID")
            record = _locate_raw_record(document, binding, reasons)
            if record is None:
                continue
            raw_record_sha = _stable_sha256(record)
            legacy_fingerprint = legacy_raw_closed_trade_identity_fingerprint_v1(record)
            if binding.get("raw_record_sha256") != raw_record_sha:
                reasons.append("RAW_RECORD_SHA256_MISMATCH")
            if not (
                binding.get("legacy_identity_fingerprint") == legacy_fingerprint
                and binding.get("record_fingerprint") == legacy_fingerprint
            ):
                reasons.append("RAW_IDENTITY_FINGERPRINT_MISMATCH")
            descriptors_value = binding.get("path_bindings")
            if not isinstance(descriptors_value, list) or not descriptors_value or any(
                not isinstance(item, Mapping) for item in descriptors_value
            ):
                reasons.append("RAW_PATH_DESCRIPTORS_REQUIRED")
                continue
            descriptors = list(descriptors_value)
            paths = [str(item.get("path") or "") for item in descriptors]
            if len(paths) != len(set(paths)):
                reasons.append("RAW_PATH_DESCRIPTOR_DUPLICATE")
            if proposal_type == "LEGACY_ALIAS_CANONICALIZATION":
                _validate_legacy_proposal_paths(proposal, record, descriptors, reasons)
            elif proposal_type == "FINANCIAL_OUTCOME_CANONICALIZATION":
                _validate_financial_proposal_paths(proposal, record, descriptors, reasons)
            else:
                reasons.append("PROPOSAL_TYPE_UNSUPPORTED")
            validated_bindings.append(_canonical_copy(binding))

    reasons[:] = sorted(set(reasons))
    if reasons or len(validated_bindings) != len(proposals):
        if not reasons:
            reasons.append("ONE_OR_MORE_RAW_PATH_BINDINGS_FAILED")
        return base

    translation_request = {
        "request_version": "DORMANT_RAW_PATH_BOUND_TRANSLATION_REQUEST_V1",
        "plan_sha256": supplied_plan_sha,
        "raw_registry_document_sha256": supplied_document_sha,
        "raw_registry_snapshot_envelope_sha256": supplied_snapshot_sha,
        "closed_collection_locator_sha256": supplied_locator_sha,
        "raw_path_inventory_sha256": supplied_inventory_sha,
        "raw_path_receipt_sha256": supplied_inventory_sha,
        "binding_count": len(validated_bindings),
        "bindings": validated_bindings,
        "preservation_invariants": {
            "whole_registry_preimage_bound": True,
            "open_trades_must_remain_exact": True,
            "non_target_closed_records_must_remain_exact": True,
            "top_level_fields_must_remain_exact": True,
            "collection_shape_order_and_keys_must_remain_exact": True,
            "ownership_order_and_protection_fields_must_remain_exact": True,
            "only_explicitly_bound_paths_may_be_considered": True,
        },
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "translation_allowed": False,
        "apply_allowed": False,
        "write_executed": False,
    }
    translation_request["translation_request_sha256"] = _stable_sha256(
        translation_request
    )
    base.update(
        {
            "ok": True,
            "binding_verification_allowed": True,
            "bindings_valid": True,
            "translation_allowed": False,
            "apply_allowed": False,
            "status": "CLOSED_IDENTITY_CONFLICT_RAW_PATHS_BOUND_OFFLINE_TRANSLATION_BLOCKED",
            "reasons": [],
            "translation_request": translation_request,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PATH_BINDING_CONTRACT_V1_VERSION",
    "bind_closed_identity_conflict_raw_paths_offline_v1",
    "legacy_raw_closed_trade_identity_fingerprint_v1",
    "raw_closed_collection_locator_sha256_v1",
    "raw_path_binding_inventory_sha256_v1",
    "raw_path_binding_sha256_v1",
    "raw_registry_document_sha256_v1",
    "raw_registry_snapshot_envelope_sha256_v1",
    "repair_plan_sha256_v1",
]
