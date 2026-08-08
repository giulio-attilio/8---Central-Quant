"""Read-only V1 migration audit for the dormant Registry V2 project.

The public API reads one explicitly supplied local V1 snapshot and returns a
deterministic in-memory proposal.  It never writes V1/V2 state, generates an
operational identity, or performs migration.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from registry_execution_schema import is_logical_trade_id


STRONG_LIFECYCLE_ID = "STRONG_LIFECYCLE_ID"
STRONG_IDENTITY_PARTIAL = "STRONG_IDENTITY_PARTIAL"
LEGACY_LOGICAL_ONLY = "LEGACY_LOGICAL_ONLY"
AMBIGUOUS_IDENTITY = "AMBIGUOUS_IDENTITY"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
MISSING_IDENTITY = "MISSING_IDENTITY"
MODE_CONFLICT = "MODE_CONFLICT"
EXTERNAL_OR_MANUAL = "EXTERNAL_OR_MANUAL"
INVALID_ROW = "INVALID_ROW"

V2_PROJECTION_CANDIDATE = "V2_PROJECTION_CANDIDATE"
ARCHIVE_READ_ONLY = "ARCHIVE_READ_ONLY"
ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION = "ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION"
QUARANTINE = "QUARANTINE"
EXTERNAL_OBSERVATION_ONLY = "EXTERNAL_OBSERVATION_ONLY"
INVALID_DO_NOT_MIGRATE = "INVALID_DO_NOT_MIGRATE"

PAPER = "PAPER"
REAL = "REAL"
VERIFY = "VERIFY"
UNKNOWN = "UNKNOWN"

REGISTRY_V2_MIGRATION_AUDIT_OK = "REGISTRY_V2_MIGRATION_AUDIT_OK"
REGISTRY_V2_MIGRATION_FILE_NOT_FOUND = "REGISTRY_V2_MIGRATION_FILE_NOT_FOUND"
REGISTRY_V2_MIGRATION_FILE_INVALID_JSON = "REGISTRY_V2_MIGRATION_FILE_INVALID_JSON"
REGISTRY_V2_MIGRATION_DOCUMENT_INVALID = "REGISTRY_V2_MIGRATION_DOCUMENT_INVALID"

# Short aliases keep the public status names convenient without introducing a
# second status vocabulary.
MIGRATION_AUDIT_OK = REGISTRY_V2_MIGRATION_AUDIT_OK
MIGRATION_AUDIT_FILE_NOT_FOUND = REGISTRY_V2_MIGRATION_FILE_NOT_FOUND
MIGRATION_AUDIT_FILE_INVALID_JSON = REGISTRY_V2_MIGRATION_FILE_INVALID_JSON
MIGRATION_AUDIT_DOCUMENT_INVALID = REGISTRY_V2_MIGRATION_DOCUMENT_INVALID

_IDENTITY_FIELDS = (
    "trade_id",
    "lifecycle_id",
    "client_order_id",
    "broker_order_id",
    "exchange_order_id",
    "fill_id",
    "symbol",
    "side",
    "bot",
    "setup",
)
_FIELD_ALIASES = {
    "trade_id": ("trade_id", "logical_trade_id"),
    "lifecycle_id": ("lifecycle_id", "lifecycle_uuid", "lifecycle", "execution_id"),
    "client_order_id": ("client_order_id", "clientOrderId"),
    "broker_order_id": ("broker_order_id", "brokerOrderId", "order_id"),
    "exchange_order_id": ("exchange_order_id", "exchangeOrderId"),
    "fill_id": ("fill_id", "fill_ids", "fills"),
    "symbol": ("symbol",),
    "side": ("side",),
    "bot": ("bot",),
    "setup": ("setup",),
    "execution_mode": ("execution_mode", "mode"),
    "registry_mode": ("registry_mode",),
}
_MODE_FIELDS = ("execution_mode", "registry_mode")
_IDENTITY_STRONG_FIELDS = ("client_order_id", "broker_order_id", "exchange_order_id", "fill_id")
_FACTUAL_BROKER_EVIDENCE_FIELDS = ("broker_order_id", "exchange_order_id", "fill_id")
_EXTERNAL_KEYS = {
    "manual_position",
    "external_position",
    "manual",
    "external",
    "is_manual",
    "is_external",
}


@dataclass(frozen=True)
class MigrationAuditRecord:
    audit_id: str
    source_collection: str
    source_locator: str
    raw_trade_id: str | None
    logical_trade_id: str | None
    classification: str
    proposed_execution_id: str | None
    identity_source: str | None
    strong_ids: tuple[str, ...]
    mode_claim: str | None
    mode_evidence: tuple[str, ...]
    recommendation: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MigrationCollisionGroup:
    logical_trade_id: str
    candidate_count: int
    source_locations: tuple[str, ...]
    collections: tuple[str, ...]
    strong_ids: tuple[str, ...]
    collision_risk: bool


@dataclass(frozen=True)
class MigrationAuditResult:
    ok: bool
    status: str
    path: str
    source_digest: str | None
    open_count: int
    closed_count: int
    total_records: int
    classification_counts: dict[str, int]
    collision_groups: tuple[MigrationCollisionGroup, ...]
    records: tuple[MigrationAuditRecord, ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def compute_legacy_row_digest(row: Mapping[str, Any]) -> str:
    """Return the deterministic canonical JSON SHA-256 digest of one V1 row."""

    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    encoded = json.dumps(
        row,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_legacy_audit_id(
    source_digest: str,
    source_collection: str,
    source_locator: str,
    row_digest: str,
) -> str:
    """Build a report-only deterministic ``legacyaudit_<sha256>`` identifier."""

    payload = "\n".join((source_digest, source_collection, source_locator, row_digest))
    return "legacyaudit_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_registry_v1_for_v2(path: Any) -> MigrationAuditResult:
    """Audit one explicitly supplied local V1 JSON snapshot in memory only."""

    path_text = str(path)
    if _is_non_local_path(path):
        return _empty_result(False, MIGRATION_AUDIT_DOCUMENT_INVALID, path_text, ("path_must_be_local",))

    try:
        path_object = Path(path)
        with path_object.open("rb") as handle:
            raw_bytes = handle.read()
    except FileNotFoundError:
        return _empty_result(False, MIGRATION_AUDIT_FILE_NOT_FOUND, path_text, ("file_not_found",))
    except (OSError, TypeError, ValueError):
        return _empty_result(False, MIGRATION_AUDIT_DOCUMENT_INVALID, path_text, ("file_read_failed",))

    source_digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        document = json.loads(raw_bytes.decode("utf-8"), parse_constant=_reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _empty_result(False, MIGRATION_AUDIT_FILE_INVALID_JSON, path_text, ("invalid_json",), source_digest)

    if not isinstance(document, Mapping):
        return _empty_result(False, MIGRATION_AUDIT_DOCUMENT_INVALID, path_text, ("top_level_mapping_required",), source_digest)
    if not isinstance(document.get("open_trades"), Mapping):
        return _empty_result(False, MIGRATION_AUDIT_DOCUMENT_INVALID, path_text, ("open_trades:mapping_required",), source_digest)
    if not isinstance(document.get("closed_trades"), (Mapping, list)):
        return _empty_result(False, MIGRATION_AUDIT_DOCUMENT_INVALID, path_text, ("closed_trades:mapping_or_list_required",), source_digest)

    candidates = []
    candidates.extend(_iter_collection(document["open_trades"], "open_trades"))
    candidates.extend(_iter_collection(document["closed_trades"], "closed_trades"))
    records = []
    for collection, locator, source_key, row in candidates:
        records.append(_audit_one_row(source_digest, collection, locator, source_key, row))

    records = _flag_duplicate_strong_ids(records)
    collision_groups = _build_collision_groups(records)
    counts = dict(Counter(record.classification for record in records))
    warnings = []
    if collision_groups:
        warnings.append("logical_trade_id_collision_groups_present")
    if any(record.classification == IDENTITY_CONFLICT for record in records):
        warnings.append("identity_conflicts_present")
    if any(record.classification == MODE_CONFLICT for record in records):
        warnings.append("mode_conflicts_present")
    return MigrationAuditResult(
        ok=True,
        status=MIGRATION_AUDIT_OK,
        path=path_text,
        source_digest=source_digest,
        open_count=sum(1 for item in candidates if item[0] == "open_trades"),
        closed_count=sum(1 for item in candidates if item[0] == "closed_trades"),
        total_records=len(records),
        classification_counts=counts,
        collision_groups=tuple(collision_groups),
        records=tuple(records),
        warnings=tuple(warnings),
    )


def _audit_one_row(
    source_digest: str,
    collection: str,
    locator: str,
    source_key: Any,
    row: Any,
) -> MigrationAuditRecord:
    row_digest = _safe_row_digest(row)
    audit_id = build_legacy_audit_id(source_digest, collection, locator, row_digest)
    if not isinstance(row, Mapping):
        return MigrationAuditRecord(
            audit_id=audit_id,
            source_collection=collection,
            source_locator=locator,
            raw_trade_id=_string_or_none(source_key),
            logical_trade_id=None,
            classification=INVALID_ROW,
            proposed_execution_id=None,
            identity_source=None,
            strong_ids=(),
            mode_claim=None,
            mode_evidence=(),
            recommendation=INVALID_DO_NOT_MIGRATE,
            errors=("row_mapping_required",),
        )

    aliases, alias_errors = _resolve_aliases(row)
    raw_trade_id = _first_value(aliases["trade_id"], source_key)
    logical_trade_id = _resolve_logical_trade_id(row, raw_trade_id)
    identity_strong_ids = _id_values(aliases, _IDENTITY_STRONG_FIELDS)
    factual_broker_ids = _id_values(aliases, _FACTUAL_BROKER_EVIDENCE_FIELDS)
    lifecycle_id = _single_value(aliases["lifecycle_id"])
    strong_ids = ([f"lifecycle_id={lifecycle_id}"] if lifecycle_id else []) + identity_strong_ids
    external = _is_external(row)
    mode_claim, mode_evidence, mode_error = _audit_mode(row, aliases, factual_broker_ids)
    mode_alias_errors = tuple(error for error in alias_errors if error.startswith("mode_alias_conflict:"))
    identity_alias_errors = tuple(error for error in alias_errors if not error.startswith("mode_alias_conflict:"))
    errors = list(identity_alias_errors)
    if mode_alias_errors and mode_error is None:
        mode_error = mode_alias_errors[0]
    if mode_error:
        errors.append(mode_error)

    if external:
        classification = EXTERNAL_OR_MANUAL
        recommendation = EXTERNAL_OBSERVATION_ONLY
    elif identity_alias_errors:
        classification = IDENTITY_CONFLICT
        recommendation = QUARANTINE
    elif mode_error:
        classification = MODE_CONFLICT
        recommendation = QUARANTINE
    else:
        if lifecycle_id:
            classification = STRONG_LIFECYCLE_ID
            recommendation = V2_PROJECTION_CANDIDATE
        elif strong_ids:
            classification = STRONG_IDENTITY_PARTIAL
            recommendation = ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION
        elif logical_trade_id:
            classification = LEGACY_LOGICAL_ONLY
            recommendation = ARCHIVE_READ_ONLY
        elif raw_trade_id:
            classification = AMBIGUOUS_IDENTITY
            recommendation = QUARANTINE
        else:
            classification = MISSING_IDENTITY
            recommendation = INVALID_DO_NOT_MIGRATE

    proposed_execution_id = None
    identity_source = None
    if classification == STRONG_LIFECYCLE_ID:
        proposed_execution_id = lifecycle_id
        identity_source = "LEGACY_LIFECYCLE_ID"

    warnings = []
    if classification == STRONG_IDENTITY_PARTIAL:
        warnings.append("ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION")
    return MigrationAuditRecord(
        audit_id=audit_id,
        source_collection=collection,
        source_locator=locator,
        raw_trade_id=_string_or_none(raw_trade_id),
        logical_trade_id=logical_trade_id,
        classification=classification,
        proposed_execution_id=proposed_execution_id,
        identity_source=identity_source,
        strong_ids=tuple(strong_ids),
        mode_claim=mode_claim,
        mode_evidence=tuple(mode_evidence),
        recommendation=recommendation,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _iter_collection(collection: Any, collection_name: str):
    if isinstance(collection, Mapping):
        for key, row in collection.items():
            yield collection_name, f"{collection_name}.{key}", key, row
    else:
        for index, row in enumerate(collection):
            yield collection_name, f"{collection_name}[{index}]", index, row


def _resolve_aliases(row: Mapping[str, Any]) -> tuple[dict[str, list[Any]], tuple[str, ...]]:
    metadata = row.get("metadata")
    sources = [row]
    if isinstance(metadata, Mapping):
        sources.append(metadata)
    aliases = {field: [] for field in (*_IDENTITY_FIELDS, *_MODE_FIELDS)}
    for field, names in _FIELD_ALIASES.items():
        for source in sources:
            for name in names:
                if name in source:
                    value = source[name]
                    if field == "fill_id":
                        aliases[field].extend(_extract_fill_ids(value))
                    elif value is not None:
                        aliases[field].append(value)
    errors = []
    for field in _IDENTITY_FIELDS:
        if len(_distinct_values(aliases[field])) > 1:
            errors.append(f"alias_conflict:{field}")
    for field in _MODE_FIELDS:
        if len(_distinct_values(aliases[field])) > 1:
            errors.append(f"mode_alias_conflict:{field}")
    return aliases, tuple(errors)


def _audit_mode(
    row: Mapping[str, Any],
    aliases: Mapping[str, list[Any]],
    strong_ids: Sequence[str],
) -> tuple[str, tuple[str, ...], str | None]:
    claims = []
    for field in _MODE_FIELDS:
        value = _single_value(aliases[field])
        if value:
            claims.append((field, str(value).strip().upper()))
    evidence = [f"explicit:{field}={value}" for field, value in claims]
    has_broker_evidence = bool(strong_ids)
    if any(value in {"PAPER", "VERIFY"} for _, value in claims) and has_broker_evidence:
        evidence.append("broker_evidence:strong_id")
        return MODE_CONFLICT, tuple(evidence), "mode_conflict:paper_or_verify_with_broker_evidence"
    if any(value in {"LIVE", "REAL"} for _, value in claims) and has_broker_evidence:
        evidence.append("broker_evidence:strong_id")
        return REAL, tuple(evidence), None
    if any(value == "PAPER" for _, value in claims):
        return PAPER, tuple(evidence), None
    if any(value == "VERIFY" for _, value in claims):
        return VERIFY, tuple(evidence), None
    if any(value in {"LIVE", "REAL"} for _, value in claims):
        evidence.append("explicit_live_or_real_without_factual_broker_evidence")
        return UNKNOWN, tuple(evidence), None
    return UNKNOWN, tuple(evidence), None


def _resolve_logical_trade_id(row: Mapping[str, Any], raw_trade_id: Any) -> str | None:
    candidates = []
    for value in (row.get("logical_trade_id"), raw_trade_id):
        if isinstance(value, str) and is_logical_trade_id(value):
            candidates.append(value)
    if len(set(candidates)) > 1:
        return None
    if candidates:
        return candidates[0]
    parts = (row.get("bot"), row.get("setup"), row.get("symbol"), row.get("side"))
    if all(isinstance(value, str) and value.strip() for value in parts):
        candidate = ":".join(value.strip().upper() for value in parts)
        if is_logical_trade_id(candidate):
            return candidate
    return None


def _id_values(aliases: Mapping[str, list[Any]], fields: Sequence[str]) -> list[str]:
    values = []
    for field in fields:
        for value in aliases[field]:
            if isinstance(value, str) and value.strip():
                values.append(f"{field}={value.strip()}")
    return list(dict.fromkeys(values))


def _is_external(row: Mapping[str, Any]) -> bool:
    for key, value in row.items():
        normalized_key = str(key).lower()
        if normalized_key in _EXTERNAL_KEYS and value is True:
            return True
    owner = row.get("owner_type")
    if isinstance(owner, str) and owner.upper() in {"MANUAL", "EXTERNAL", "MANUAL_EXTERNAL"}:
        return True
    if row.get("managed_by_central") is False:
        return True
    metadata = row.get("metadata")
    return isinstance(metadata, Mapping) and _is_external(metadata)


def _flag_duplicate_strong_ids(records: list[MigrationAuditRecord]) -> list[MigrationAuditRecord]:
    occurrences: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        for strong_id in record.strong_ids:
            occurrences[strong_id].append(index)
    duplicate_indexes = {index for indexes in occurrences.values() if len(indexes) > 1 for index in indexes}
    if not duplicate_indexes:
        return records
    flagged = []
    for index, record in enumerate(records):
        if index not in duplicate_indexes or record.classification == EXTERNAL_OR_MANUAL:
            flagged.append(record)
            continue
        flagged.append(
            replace(
                record,
                classification=IDENTITY_CONFLICT,
                proposed_execution_id=None,
                identity_source=None,
                recommendation=QUARANTINE,
                errors=record.errors + ("duplicate_strong_identity",),
            )
        )
    return flagged


def _build_collision_groups(records: Sequence[MigrationAuditRecord]) -> list[MigrationCollisionGroup]:
    grouped: dict[str, list[MigrationAuditRecord]] = defaultdict(list)
    for record in records:
        if record.logical_trade_id:
            grouped[record.logical_trade_id].append(record)
    groups = []
    for logical_id, candidates in grouped.items():
        if len(candidates) < 2:
            continue
        groups.append(
            MigrationCollisionGroup(
                logical_trade_id=logical_id,
                candidate_count=len(candidates),
                source_locations=tuple(candidate.source_locator for candidate in candidates),
                collections=tuple(candidate.source_collection for candidate in candidates),
                strong_ids=tuple(sorted({strong_id for candidate in candidates for strong_id in candidate.strong_ids})),
                collision_risk=True,
            )
        )
    return groups


def _extract_fill_ids(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        if value.get("fill_id") is not None:
            return [value["fill_id"]]
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        output = []
        for item in value:
            output.extend(_extract_fill_ids(item))
        return output
    return []


def _safe_row_digest(row: Any) -> str:
    if not isinstance(row, Mapping):
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    try:
        return compute_legacy_row_digest(row)
    except (TypeError, ValueError):
        return hashlib.sha256(repr(row).encode("utf-8")).hexdigest()


def _distinct_values(values: Sequence[Any]) -> list[Any]:
    distinct = []
    for value in values:
        if not any(value == existing for existing in distinct):
            distinct.append(value)
    return distinct


def _single_value(values: Sequence[Any]) -> Any:
    distinct = _distinct_values(values)
    return distinct[0] if len(distinct) == 1 else None


def _first_value(values: Sequence[Any], fallback: Any) -> Any:
    return values[0] if values else fallback


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else (str(value) if value is not None else None)


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _is_non_local_path(path: Any) -> bool:
    return isinstance(path, str) and "://" in path


def _empty_result(ok: bool, status: str, path: str, errors: tuple[str, ...], source_digest: str | None = None) -> MigrationAuditResult:
    return MigrationAuditResult(
        ok=ok,
        status=status,
        path=path,
        source_digest=source_digest,
        open_count=0,
        closed_count=0,
        total_records=0,
        classification_counts={},
        collision_groups=(),
        records=(),
        errors=errors,
    )


__all__ = (
    "AMBIGUOUS_IDENTITY",
    "ARCHIVE_READ_ONLY",
    "ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION",
    "EXTERNAL_OBSERVATION_ONLY",
    "EXTERNAL_OR_MANUAL",
    "IDENTITY_CONFLICT",
    "INVALID_DO_NOT_MIGRATE",
    "INVALID_ROW",
    "LEGACY_LOGICAL_ONLY",
    "MIGRATION_AUDIT_DOCUMENT_INVALID",
    "MIGRATION_AUDIT_FILE_INVALID_JSON",
    "MIGRATION_AUDIT_FILE_NOT_FOUND",
    "MIGRATION_AUDIT_OK",
    "MODE_CONFLICT",
    "MISSING_IDENTITY",
    "MigrationAuditRecord",
    "MigrationAuditResult",
    "MigrationCollisionGroup",
    "QUARANTINE",
    "REGISTRY_V2_MIGRATION_AUDIT_OK",
    "REGISTRY_V2_MIGRATION_DOCUMENT_INVALID",
    "REGISTRY_V2_MIGRATION_FILE_INVALID_JSON",
    "REGISTRY_V2_MIGRATION_FILE_NOT_FOUND",
    "STRONG_IDENTITY_PARTIAL",
    "STRONG_LIFECYCLE_ID",
    "PAPER",
    "REAL",
    "UNKNOWN",
    "VERIFY",
    "V2_PROJECTION_CANDIDATE",
    "audit_registry_v1_for_v2",
    "build_legacy_audit_id",
    "compute_legacy_row_digest",
)
