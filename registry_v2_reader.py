"""Strictly read-only V2 snapshot reader.

The caller must provide a local path explicitly.  This module parses one JSON
snapshot, validates its structural contract, rebuilds V2.1 indexes in memory,
and never changes the file or the parsed document.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from registry_execution_schema import (
    CLOSED_PROVISIONAL,
    CLOSED_RECONCILED,
    REGISTRY_VERSION,
    SCHEMA_VERSION,
    build_registry_v2_indexes,
    validate_registry_execution_row,
)


REGISTRY_V2_READ_OK = "REGISTRY_V2_READ_OK"
REGISTRY_V2_FILE_NOT_FOUND = "REGISTRY_V2_FILE_NOT_FOUND"
REGISTRY_V2_FILE_INVALID_JSON = "REGISTRY_V2_FILE_INVALID_JSON"
REGISTRY_V2_DOCUMENT_INVALID = "REGISTRY_V2_DOCUMENT_INVALID"
REGISTRY_V2_SCHEMA_VERSION_UNSUPPORTED = "REGISTRY_V2_SCHEMA_VERSION_UNSUPPORTED"
REGISTRY_V2_REGISTRY_VERSION_UNSUPPORTED = "REGISTRY_V2_REGISTRY_VERSION_UNSUPPORTED"
REGISTRY_V2_GENERATION_INVALID = "REGISTRY_V2_GENERATION_INVALID"
REGISTRY_V2_SNAPSHOT_DIGEST_INVALID = "REGISTRY_V2_SNAPSHOT_DIGEST_INVALID"
REGISTRY_V2_INDEX_MISMATCH = "REGISTRY_V2_INDEX_MISMATCH"
REGISTRY_V2_ROW_INVALID = "REGISTRY_V2_ROW_INVALID"

_DOCUMENT_FIELDS = (
    "schema_version",
    "registry_version",
    "generation",
    "snapshot_id",
    "updated_at",
    "integrity",
    "wal",
    "open_trades",
    "closed_trades",
    "external_observations",
    "indexes",
    "operation_ledger",
    "migration",
)
_INDEX_NAMES = (
    "by_execution_id",
    "by_lifecycle_id_alias",
    "by_logical_trade_id",
    "by_bot",
    "by_symbol",
    "by_bot_symbol",
    "by_bot_symbol_side",
    "by_owner_type",
    "by_state",
    "by_signal_id",
    "by_decision_id",
)
_COMPOSITE_INDEX_NAMES = {"by_bot_symbol", "by_bot_symbol_side"}


@dataclass(frozen=True)
class RegistryV2ReadResult:
    """Immutable result envelope for one read-only snapshot attempt."""

    ok: bool
    status: str
    path: str
    schema_version: str | None = None
    registry_version: str | None = None
    generation: int | None = None
    snapshot_id: str | None = None
    snapshot_digest: str | None = None
    open_count: int = 0
    closed_count: int = 0
    external_count: int = 0
    indexes_rebuilt: bool = False
    index_match: bool | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    document: Mapping[str, Any] | None = None


def compute_registry_v2_snapshot_digest(document: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 snapshot digest.

    The input is deep-copied, ``integrity.snapshot_digest`` is removed from
    that copy, and the remainder is serialized with sorted keys, compact
    separators, UTF-8 characters preserved, and non-finite numbers disabled.
    The resulting UTF-8 bytes are hashed with SHA-256.
    """

    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    payload = copy.deepcopy(document)
    integrity = payload.get("integrity")
    if not isinstance(integrity, Mapping):
        raise ValueError("document.integrity must be a mapping")
    digest_free_integrity = dict(integrity)
    digest_free_integrity.pop("snapshot_digest", None)
    payload["integrity"] = digest_free_integrity
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_indexes_for_json(indexes: Mapping[str, Mapping[Any, Any]]) -> dict[str, dict[str, Any]]:
    """Project V2.1 in-memory indexes to the canonical JSON representation.

    ``by_execution_id`` stores ``execution_id -> execution_id`` because the
    row itself is already stored in a collection.  Alias and grouping indexes
    store execution IDs.  Composite keys use ``BOT|SYMBOL`` and
    ``BOT|SYMBOL|SIDE``; non-unique values are JSON lists preserving order.
    Unknown future index names are not projected.
    """

    if not isinstance(indexes, Mapping):
        raise TypeError("indexes must be a mapping")
    projected: dict[str, dict[str, Any]] = {}
    for name in _INDEX_NAMES:
        source = indexes.get(name)
        if not isinstance(source, Mapping):
            raise ValueError(f"missing index: {name}")
        output: dict[str, Any] = {}
        for key, value in source.items():
            json_key = _index_key_to_json(name, key)
            if name == "by_execution_id":
                output[json_key] = json_key
            elif name == "by_lifecycle_id_alias":
                output[json_key] = value
            else:
                output[json_key] = list(value)
        projected[name] = output
    return projected


def read_registry_v2(path: Any) -> RegistryV2ReadResult:
    """Read and validate one explicitly supplied local V2 snapshot path."""

    path_text = str(path)
    if _is_non_local_path(path):
        return _result(False, REGISTRY_V2_DOCUMENT_INVALID, path_text, errors=("path_must_be_local",))

    try:
        path_object = Path(path)
        with path_object.open("r", encoding="utf-8") as handle:
            document = json.load(handle, parse_constant=_reject_non_finite)
    except FileNotFoundError:
        return _result(False, REGISTRY_V2_FILE_NOT_FOUND, path_text, errors=("file_not_found",))
    except (json.JSONDecodeError, ValueError):
        return _result(False, REGISTRY_V2_FILE_INVALID_JSON, path_text, errors=("invalid_json",))
    except (OSError, TypeError):
        return _result(False, REGISTRY_V2_DOCUMENT_INVALID, path_text, errors=("file_read_failed",))

    return _validate_document(document, path_text)


def _validate_document(document: Any, path_text: str) -> RegistryV2ReadResult:
    if not isinstance(document, Mapping):
        return _result(False, REGISTRY_V2_DOCUMENT_INVALID, path_text, errors=("top_level_mapping_required",))

    missing = tuple(field for field in _DOCUMENT_FIELDS if field not in document)
    if missing:
        return _result(False, REGISTRY_V2_DOCUMENT_INVALID, path_text, errors=missing, document=document)

    if document.get("schema_version") != SCHEMA_VERSION:
        return _result(
            False,
            REGISTRY_V2_SCHEMA_VERSION_UNSUPPORTED,
            path_text,
            schema_version=_optional_string(document.get("schema_version")),
            errors=("schema_version",),
            document=document,
        )
    if document.get("registry_version") != REGISTRY_VERSION:
        return _result(
            False,
            REGISTRY_V2_REGISTRY_VERSION_UNSUPPORTED,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=_optional_string(document.get("registry_version")),
            errors=("registry_version",),
            document=document,
        )

    generation = document.get("generation")
    if type(generation) is not int or generation < 0:
        return _result(
            False,
            REGISTRY_V2_GENERATION_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            errors=("generation",),
            document=document,
        )

    snapshot_id = document.get("snapshot_id")
    if not _nonempty_string(snapshot_id):
        return _result(
            False,
            REGISTRY_V2_DOCUMENT_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            errors=("snapshot_id",),
            document=document,
        )

    structural_errors = _validate_structural_mappings(document)
    if structural_errors:
        return _result(
            False,
            REGISTRY_V2_DOCUMENT_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            errors=structural_errors,
            document=document,
        )

    integrity = document["integrity"]
    snapshot_digest = integrity.get("snapshot_digest")
    if not _nonempty_string(snapshot_digest):
        return _result(
            False,
            REGISTRY_V2_SNAPSHOT_DIGEST_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            errors=("integrity.snapshot_digest",),
            document=document,
        )
    try:
        computed_digest = compute_registry_v2_snapshot_digest(document)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _result(
            False,
            REGISTRY_V2_SNAPSHOT_DIGEST_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            errors=("integrity.snapshot_digest_uncomputable",),
            document=document,
        )
    if snapshot_digest != computed_digest:
        return _result(
            False,
            REGISTRY_V2_SNAPSHOT_DIGEST_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            errors=("integrity.snapshot_digest_mismatch",),
            document=document,
        )

    wal_errors, wal_warnings = _validate_wal(document["wal"])
    if wal_errors:
        return _result(
            False,
            REGISTRY_V2_DOCUMENT_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            errors=wal_errors,
            warnings=wal_warnings,
            document=document,
        )

    open_rows, open_errors = _validate_rows(document["open_trades"], "open_trades", open_collection=True)
    closed_rows, closed_errors = _validate_rows(document["closed_trades"], "closed_trades", open_collection=False)
    row_errors = open_errors + closed_errors
    if row_errors:
        return _result(
            False,
            REGISTRY_V2_ROW_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            open_count=len(open_rows),
            closed_count=len(closed_rows),
            errors=row_errors,
            warnings=wal_warnings,
            document=document,
        )

    all_rows = list(open_rows.values()) + list(closed_rows.values())
    try:
        rebuilt = build_registry_v2_indexes(all_rows)
        expected_indexes = project_indexes_for_json(rebuilt)
    except (TypeError, ValueError, KeyError) as error:
        return _result(
            False,
            REGISTRY_V2_ROW_INVALID,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            open_count=len(open_rows),
            closed_count=len(closed_rows),
            indexes_rebuilt=False,
            errors=(f"index_rebuild:{error}",),
            warnings=wal_warnings,
            document=document,
        )

    index_errors = _compare_persisted_indexes(document["indexes"], expected_indexes)
    if index_errors:
        return _result(
            False,
            REGISTRY_V2_INDEX_MISMATCH,
            path_text,
            schema_version=SCHEMA_VERSION,
            registry_version=REGISTRY_VERSION,
            generation=generation,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            open_count=len(open_rows),
            closed_count=len(closed_rows),
            indexes_rebuilt=True,
            index_match=False,
            errors=index_errors,
            warnings=wal_warnings,
            document=document,
        )

    return _result(
        True,
        REGISTRY_V2_READ_OK,
        path_text,
        schema_version=SCHEMA_VERSION,
        registry_version=REGISTRY_VERSION,
        generation=generation,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        open_count=len(open_rows),
        closed_count=len(closed_rows),
        external_count=len(document["external_observations"]),
        indexes_rebuilt=True,
        index_match=True,
        warnings=wal_warnings,
        document=document,
    )


def _result(ok: bool, status: str, path: str, **values: Any) -> RegistryV2ReadResult:
    return RegistryV2ReadResult(ok=ok, status=status, path=path, **values)


def _validate_structural_mappings(document: Mapping[str, Any]) -> tuple[str, ...]:
    errors = []
    for field in ("integrity", "wal", "open_trades", "closed_trades", "external_observations", "indexes", "operation_ledger", "migration"):
        if not isinstance(document.get(field), Mapping):
            errors.append(f"{field}:mapping_required")
    if not _nonempty_string(document.get("updated_at")):
        errors.append("updated_at")
    return tuple(errors)


def _validate_wal(wal: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    expected = ("materialized_seq", "materialized_event_id", "materialized_request_digest", "state")
    errors = [field for field in expected if field not in wal]
    if errors:
        return tuple(f"wal.{field}" for field in errors), ()
    sequence = wal.get("materialized_seq")
    if type(sequence) is not int or sequence < 0:
        errors.append("wal.materialized_seq")
    for field in ("materialized_event_id", "materialized_request_digest"):
        value = wal.get(field)
        if value is not None and not _nonempty_string(value):
            errors.append(f"wal.{field}")
    state = wal.get("state")
    if not _nonempty_string(state):
        errors.append("wal.state")
    warnings = () if state == "CLEAN" else ("wal.state_not_clean",)
    return tuple(errors), warnings


def _validate_rows(collection: Any, collection_name: str, *, open_collection: bool) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...]]:
    if not isinstance(collection, Mapping):
        return {}, (f"{collection_name}:mapping_required",)
    rows: dict[str, Mapping[str, Any]] = {}
    errors = []
    closed_states = {CLOSED_PROVISIONAL, CLOSED_RECONCILED}
    for execution_key, row in collection.items():
        prefix = f"{collection_name}.{execution_key}"
        if not isinstance(execution_key, str) or not execution_key:
            errors.append(f"{prefix}:execution_key_invalid")
            continue
        if not isinstance(row, Mapping):
            errors.append(f"{prefix}:row_mapping_required")
            continue
        if row.get("execution_id") != execution_key:
            errors.append(f"{prefix}:execution_key_mismatch")
        validation = validate_registry_execution_row(row)
        if not validation.ok:
            errors.extend(f"{prefix}:{error}" for error in (validation.errors or (validation.status,)))
        state = row.get("lifecycle_state")
        if open_collection and state in closed_states:
            errors.append(f"{prefix}:closed_state_in_open_trades")
        if not open_collection and state not in closed_states:
            errors.append(f"{prefix}:open_state_in_closed_trades")
        rows[execution_key] = row
    return rows, tuple(errors)


def _compare_persisted_indexes(persisted: Any, expected: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    if not isinstance(persisted, Mapping):
        return ("indexes:mapping_required",)
    errors = []
    for name in _INDEX_NAMES:
        if name not in persisted:
            errors.append(f"indexes.{name}:missing")
        elif persisted[name] != expected[name]:
            errors.append(f"indexes.{name}:mismatch")
    return tuple(errors)


def _index_key_to_json(name: str, key: Any) -> str:
    if name in _COMPOSITE_INDEX_NAMES:
        if not isinstance(key, tuple):
            raise ValueError(f"{name} key must be tuple")
        return "|".join(str(part) for part in key)
    return str(key)


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _is_non_local_path(path: Any) -> bool:
    return isinstance(path, str) and "://" in path


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__ = (
    "REGISTRY_V2_DOCUMENT_INVALID",
    "REGISTRY_V2_FILE_INVALID_JSON",
    "REGISTRY_V2_FILE_NOT_FOUND",
    "REGISTRY_V2_GENERATION_INVALID",
    "REGISTRY_V2_INDEX_MISMATCH",
    "REGISTRY_V2_READ_OK",
    "REGISTRY_V2_REGISTRY_VERSION_UNSUPPORTED",
    "REGISTRY_V2_ROW_INVALID",
    "REGISTRY_V2_SCHEMA_VERSION_UNSUPPORTED",
    "REGISTRY_V2_SNAPSHOT_DIGEST_INVALID",
    "RegistryV2ReadResult",
    "compute_registry_v2_snapshot_digest",
    "project_indexes_for_json",
    "read_registry_v2",
)
