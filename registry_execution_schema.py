"""Pure, dormant Registry Execution Identity V2.1 schema contract.

This module validates already-materialized rows and builds in-memory indexes.
It deliberately has no side-effecting capabilities.  Validation never fills
or mutates the supplied row.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from registry_execution_identity import (
    REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT,
    REGISTRY_SCHEMA_EXTERNAL_NOT_EXECUTION,
    REGISTRY_SCHEMA_FIELD_INVALID,
    REGISTRY_SCHEMA_INVALID,
    REGISTRY_SCHEMA_METADATA_CONFLICT,
    REGISTRY_SCHEMA_REQUIRED_FIELD_MISSING,
    REGISTRY_SCHEMA_VALID,
    REGISTRY_SCHEMA_VERIFY_NOT_EXECUTION,
    validate_execution_lifecycle_identity,
)


SCHEMA_VERSION = "REGISTRY_EXECUTION_IDENTITY_V2_1"
REGISTRY_VERSION = "2.1.0"

ENTRY_INTENT = "ENTRY_INTENT"
ENTRY_PENDING_RECONCILIATION = "ENTRY_PENDING_RECONCILIATION"
OPEN = "OPEN"
PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
CLOSE_PENDING_RECONCILIATION = "CLOSE_PENDING_RECONCILIATION"
CLOSED_PROVISIONAL = "CLOSED_PROVISIONAL"
CLOSED_RECONCILED = "CLOSED_RECONCILED"
QUARANTINED = "QUARANTINED"

PAPER = "PAPER"
VERIFY = "VERIFY"
LIVE = "LIVE"

REAL = "REAL"
SYNC_ONLY = "SYNC_ONLY"
UNKNOWN = "UNKNOWN"
CONFLICT = "CONFLICT"

CENTRAL = "CENTRAL"
MANUAL_EXTERNAL = "MANUAL_EXTERNAL"

LEGACY_MISSING = "LEGACY_MISSING"

LIFECYCLE_STATES = frozenset(
    {
        ENTRY_INTENT,
        ENTRY_PENDING_RECONCILIATION,
        OPEN,
        PARTIALLY_CLOSED,
        CLOSE_PENDING_RECONCILIATION,
        CLOSED_PROVISIONAL,
        CLOSED_RECONCILED,
        QUARANTINED,
    }
)
EXECUTION_MODES = frozenset({PAPER, VERIFY, LIVE})
REGISTRY_MODES = frozenset({PAPER, REAL, VERIFY, SYNC_ONLY, UNKNOWN, CONFLICT})
OWNER_TYPES = frozenset({CENTRAL, MANUAL_EXTERNAL, UNKNOWN})
SIDES = frozenset({"LONG", "SHORT"})
POSITION_SIDES = frozenset({"LONG", "SHORT", "BOTH", "NET", "UNKNOWN"})

_REQUIRED_COMMON_FIELDS = (
    "execution_id",
    "lifecycle_id",
    "logical_trade_id",
    "bot",
    "setup",
    "symbol",
    "side",
    "owner_type",
    "execution_mode",
    "registry_mode",
    "lifecycle_state",
    "execution_provenance",
)
_METADATA_CANONICAL_FIELDS = frozenset(
    {
        "execution_id",
        "lifecycle_id",
        "logical_trade_id",
        "bot",
        "setup",
        "symbol",
        "side",
        "owner_type",
        "execution_mode",
        "registry_mode",
        "lifecycle_state",
        "position_side",
        "signal_id",
        "decision_id",
        "execution_provenance",
    }
)


@dataclass(frozen=True)
class RegistrySchemaValidationResult:
    """Immutable result envelope for pure row validation."""

    ok: bool
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    execution_id: str | None = None
    lifecycle_id: str | None = None
    schema_version: str = SCHEMA_VERSION


RegistrySchemaResult = RegistrySchemaValidationResult
RegistrySchemaEnvelope = RegistrySchemaValidationResult


class RegistrySchemaIndexConflict(ValueError):
    """Raised when a unique in-memory V2.1 index cannot be built safely."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def build_logical_trade_id(bot: Any, setup: Any, symbol: Any, side: Any) -> str:
    """Build the non-unique grouping ID ``BOT:SETUP:SYMBOL:SIDE``."""

    parts = tuple(_normalize_logical_part(value, field) for value, field in (
        (bot, "bot"),
        (setup, "setup"),
        (symbol, "symbol"),
        (side, "side"),
    ))
    return ":".join(parts)


def is_logical_trade_id(value: Any) -> bool:
    """Return whether *value* is a canonical logical grouping ID.

    This predicate only checks grouping syntax.  It never treats a logical ID
    as an execution identity and never infers ownership or lifecycle.
    """

    if not isinstance(value, str):
        return False
    parts = value.split(":")
    return len(parts) == 4 and all(
        part and part == part.strip() and part == part.upper() and ":" not in part
        for part in parts
    )


def validate_registry_execution_row(
    row: Mapping[str, Any],
    *,
    legacy_missing_marker: str = LEGACY_MISSING,
) -> RegistrySchemaValidationResult:
    """Validate one canonical execution row without changing or enriching it."""

    if not isinstance(row, Mapping):
        return _result(False, REGISTRY_SCHEMA_FIELD_INVALID, ("row",))

    missing = tuple(field for field in _REQUIRED_COMMON_FIELDS if not _present(row, field))
    if missing:
        return _result(False, REGISTRY_SCHEMA_REQUIRED_FIELD_MISSING, missing, row=row)

    execution_id = row.get("execution_id")
    lifecycle_id = row.get("lifecycle_id")
    identity = validate_execution_lifecycle_identity(
        execution_id=execution_id,
        lifecycle_id=lifecycle_id,
        require_identity=True,
    )
    if not identity.ok:
        return _result(
            False,
            identity.status,
            identity.diagnostics or ("execution_lifecycle_identity_invalid",),
            row=row,
            execution_id=identity.execution_id,
            lifecycle_id=identity.lifecycle_id,
        )

    field_errors = []
    for field in ("execution_id", "lifecycle_id", "logical_trade_id", "bot", "setup", "symbol", "side", "owner_type", "execution_mode", "registry_mode", "lifecycle_state"):
        if not _nonempty_string(row.get(field)):
            field_errors.append(field)

    if row.get("side") not in SIDES:
        field_errors.append("side")
    if row.get("owner_type") not in OWNER_TYPES:
        field_errors.append("owner_type")
    if row.get("execution_mode") not in EXECUTION_MODES:
        field_errors.append("execution_mode")
    if row.get("registry_mode") not in REGISTRY_MODES:
        field_errors.append("registry_mode")
    if row.get("lifecycle_state") not in LIFECYCLE_STATES:
        field_errors.append("lifecycle_state")
    if not _nonempty_value(row.get("execution_provenance")):
        field_errors.append("execution_provenance")

    if row.get("logical_trade_id") != _safe_logical_trade_id(row):
        field_errors.append("logical_trade_id")

    mode = row.get("execution_mode")
    owner_type = row.get("owner_type")
    if mode == VERIFY:
        return _result(False, REGISTRY_SCHEMA_VERIFY_NOT_EXECUTION, ("execution_mode",), row=row, identity=identity)
    if owner_type == MANUAL_EXTERNAL:
        return _result(False, REGISTRY_SCHEMA_EXTERNAL_NOT_EXECUTION, ("owner_type",), row=row, identity=identity)

    if mode in {PAPER, LIVE} and owner_type != CENTRAL:
        field_errors.append("owner_type")

    if mode == PAPER and row.get("registry_mode") != PAPER:
        field_errors.append("registry_mode")
    elif mode == LIVE and row.get("registry_mode") not in {UNKNOWN, REAL, CONFLICT}:
        field_errors.append("registry_mode")

    if mode == LIVE:
        for field in ("signal_id", "decision_id", "position_side"):
            if not _nonempty_value(row.get(field)):
                field_errors.append(field)
        if row.get("position_side") not in POSITION_SIDES:
            field_errors.append("position_side")
    elif mode == PAPER:
        for field in ("signal_id", "decision_id"):
            if not _nonempty_value(row.get(field)) and not _legacy_missing_is_explicit(row, legacy_missing_marker):
                field_errors.append(field)
        if "position_side" in row and row.get("position_side") not in POSITION_SIDES:
            field_errors.append("position_side")

    metadata_status = _metadata_conflict(row)
    if metadata_status:
        return _result(False, REGISTRY_SCHEMA_METADATA_CONFLICT, (metadata_status,), row=row, identity=identity)

    if field_errors:
        return _result(
            False,
            REGISTRY_SCHEMA_FIELD_INVALID,
            tuple(dict.fromkeys(field_errors)),
            row=row,
            identity=identity,
        )

    warnings = ()
    if mode == PAPER and _legacy_missing_is_explicit(row, legacy_missing_marker):
        warnings = (LEGACY_MISSING,)
    return _result(True, REGISTRY_SCHEMA_VALID, warnings=warnings, row=row, identity=identity)


def build_registry_v2_indexes(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[Any, Any]]:
    """Build deterministic, in-memory V2.1 indexes from canonical rows.

    Unique indexes fail closed.  Non-unique indexes retain every execution in
    input order; no index chooses a first or latest row.
    """

    indexes: dict[str, dict[Any, Any]] = {
        "by_execution_id": {},
        "by_lifecycle_id_alias": {},
        "by_logical_trade_id": {},
        "by_bot": {},
        "by_symbol": {},
        "by_bot_symbol": {},
        "by_bot_symbol_side": {},
        "by_owner_type": {},
        "by_state": {},
        "by_signal_id": {},
        "by_decision_id": {},
    }
    grouped = {name: {} for name in tuple(indexes) if name != "by_execution_id" and name != "by_lifecycle_id_alias"}

    for row in rows:
        result = validate_registry_execution_row(row)
        if not result.ok:
            raise RegistrySchemaIndexConflict(result.status, f"invalid canonical row: {result.errors}")
        execution_id = result.execution_id
        lifecycle_id = result.lifecycle_id
        if execution_id in indexes["by_execution_id"]:
            raise RegistrySchemaIndexConflict(
                "REGISTRY_SCHEMA_EXECUTION_ID_CONFLICT",
                f"duplicate execution_id: {execution_id}",
            )
        if lifecycle_id in indexes["by_lifecycle_id_alias"]:
            raise RegistrySchemaIndexConflict(
                REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT,
                f"duplicate lifecycle_id alias: {lifecycle_id}",
            )
        indexes["by_execution_id"][execution_id] = row
        indexes["by_lifecycle_id_alias"][lifecycle_id] = execution_id

        keys = {
            "by_logical_trade_id": row["logical_trade_id"],
            "by_bot": row["bot"],
            "by_symbol": row["symbol"],
            "by_bot_symbol": (row["bot"], row["symbol"]),
            "by_bot_symbol_side": (row["bot"], row["symbol"], row["side"]),
            "by_owner_type": row["owner_type"],
            "by_state": row["lifecycle_state"],
            "by_signal_id": row.get("signal_id"),
            "by_decision_id": row.get("decision_id"),
        }
        for name, key in keys.items():
            if key is None:
                continue
            grouped[name].setdefault(key, []).append(execution_id)

    for name, values in grouped.items():
        indexes[name] = {key: tuple(execution_ids) for key, execution_ids in values.items()}
    return indexes


def _result(
    ok: bool,
    status: str,
    errors: tuple[str, ...] = (),
    *,
    warnings: tuple[str, ...] = (),
    row: Mapping[str, Any] | None = None,
    identity: Any = None,
    execution_id: str | None = None,
    lifecycle_id: str | None = None,
) -> RegistrySchemaValidationResult:
    if identity is not None:
        execution_id = identity.execution_id
        lifecycle_id = identity.lifecycle_id
    elif row is not None:
        execution_id = execution_id if execution_id is not None else _identity_value(row.get("execution_id"))
        lifecycle_id = lifecycle_id if lifecycle_id is not None else _identity_value(row.get("lifecycle_id"))
    return RegistrySchemaValidationResult(
        ok=ok,
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        execution_id=execution_id,
        lifecycle_id=lifecycle_id,
    )


def _present(row: Mapping[str, Any], field: str) -> bool:
    return field in row and _nonempty_value(row.get(field))


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_value(value: Any) -> bool:
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def _identity_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_logical_part(value: Any, field: str) -> str:
    if not _nonempty_string(value):
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip().upper()
    if ":" in normalized:
        raise ValueError(f"{field} cannot contain ':'")
    return normalized


def _safe_logical_trade_id(row: Mapping[str, Any]) -> str | None:
    try:
        return build_logical_trade_id(row.get("bot"), row.get("setup"), row.get("symbol"), row.get("side"))
    except (TypeError, ValueError):
        return None


def _legacy_missing_is_explicit(row: Mapping[str, Any], marker: str) -> bool:
    if row.get("legacy_missing") is True:
        return True
    if row.get("legacy_missing_marker") == marker:
        return True
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get("legacy_missing") is True or metadata.get("legacy_missing_marker") == marker
    return False


def _metadata_conflict(row: Mapping[str, Any]) -> str | None:
    metadata = row.get("metadata")
    if metadata is None:
        return None
    if not isinstance(metadata, Mapping):
        return "metadata"
    expected = {field: row.get(field) for field in _METADATA_CANONICAL_FIELDS}
    stack = [metadata]
    while stack:
        current = stack.pop()
        for key, value in current.items():
            if key in _METADATA_CANONICAL_FIELDS and value != expected[key]:
                return f"metadata.{key}"
            if isinstance(value, Mapping):
                stack.append(value)
    return None


__all__ = (
    "CENTRAL",
    "CLOSE_PENDING_RECONCILIATION",
    "CLOSED_PROVISIONAL",
    "CLOSED_RECONCILED",
    "CONFLICT",
    "ENTRY_INTENT",
    "ENTRY_PENDING_RECONCILIATION",
    "EXECUTION_MODES",
    "LEGACY_MISSING",
    "LIFECYCLE_STATES",
    "LIVE",
    "MANUAL_EXTERNAL",
    "OPEN",
    "OWNER_TYPES",
    "PAPER",
    "PARTIALLY_CLOSED",
    "POSITION_SIDES",
    "QUARANTINED",
    "REAL",
    "REGISTRY_MODES",
    "REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT",
    "REGISTRY_SCHEMA_EXTERNAL_NOT_EXECUTION",
    "REGISTRY_SCHEMA_FIELD_INVALID",
    "REGISTRY_SCHEMA_INVALID",
    "REGISTRY_SCHEMA_METADATA_CONFLICT",
    "REGISTRY_SCHEMA_REQUIRED_FIELD_MISSING",
    "REGISTRY_SCHEMA_VALID",
    "REGISTRY_SCHEMA_VERIFY_NOT_EXECUTION",
    "REGISTRY_VERSION",
    "RegistrySchemaEnvelope",
    "RegistrySchemaIndexConflict",
    "RegistrySchemaResult",
    "RegistrySchemaValidationResult",
    "SCHEMA_VERSION",
    "SIDES",
    "SYNC_ONLY",
    "UNKNOWN",
    "VERIFY",
    "build_logical_trade_id",
    "build_registry_v2_indexes",
    "is_logical_trade_id",
    "validate_registry_execution_row",
)
