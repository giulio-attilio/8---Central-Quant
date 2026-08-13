"""Generic V2.4 WAL/journal engine for explicitly injected temporary storage.

This module contains no business operation and no production path.  Callers
inject every storage path and the mutation callback; the durable authority is
an ``EVENT_COMMITTED`` journal line, while the snapshot is only a witness.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVENT_PREPARED = "EVENT_PREPARED"
SNAPSHOT_COMMITTED = "SNAPSHOT_COMMITTED"
EVENT_COMMITTED = "EVENT_COMMITTED"
WAL_EVENT_STATES = frozenset({EVENT_PREPARED, SNAPSHOT_COMMITTED, EVENT_COMMITTED})
_JOURNAL_EVENT_STATES = frozenset({EVENT_PREPARED, EVENT_COMMITTED})

CLEAN = "CLEAN"
PREPARED_PENDING = "PREPARED_PENDING"
SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT = "SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT"
JOURNAL_CORRUPT = "JOURNAL_CORRUPT"
SNAPSHOT_JOURNAL_DIVERGENCE = "SNAPSHOT_JOURNAL_DIVERGENCE"
SNAPSHOT_INVALID = "SNAPSHOT_INVALID"

WAL_OK = "WAL_OK"
WAL_CONFLICT = "WAL_CONFLICT"
WAL_RECOVERY_REQUIRED = "WAL_RECOVERY_REQUIRED"
WAL_INVALID = "WAL_INVALID"
WAL_JOURNAL_CORRUPT = "WAL_JOURNAL_CORRUPT"
WAL_SNAPSHOT_INVALID = "WAL_SNAPSHOT_INVALID"
WAL_NOT_FOUND = "WAL_NOT_FOUND"

BEFORE_PREPARED = "BEFORE_PREPARED"
AFTER_PREPARED = "AFTER_PREPARED"
DURING_TEMP_WRITE = "DURING_TEMP_WRITE"
AFTER_TEMP_FSYNC = "AFTER_TEMP_FSYNC"
AFTER_REPLACE = "AFTER_REPLACE"
BEFORE_EVENT_COMMIT = "BEFORE_EVENT_COMMIT"
AFTER_EVENT_COMMIT = "AFTER_EVENT_COMMIT"


@dataclass(frozen=True)
class RegistryV2WalStorage:
    snapshot_path: str | Path
    journal_path: str | Path
    lock_path: str | Path
    backup_dir: str | Path

    def __post_init__(self) -> None:
        for field in ("snapshot_path", "journal_path", "lock_path", "backup_dir"):
            value = getattr(self, field)
            if value is None or not str(value).strip():
                raise ValueError(f"{field} is required")
            object.__setattr__(self, field, Path(value))


@dataclass(frozen=True)
class WalEvent:
    event_seq: int
    event_id: str
    operation: str
    idempotency_key: str
    request_digest: str
    execution_id: str | None
    lifecycle_id: str | None
    expected_generation: int
    target_generation: int
    before_digest: str | None
    after_digest: str | None
    state: str
    prepared_at: str | None
    snapshot_committed_at: str | None
    committed_at: str | None
    schema_version: str
    mutation_payload: Mapping[str, Any]
    previous_committed_event_digest: str | None
    result_digest: str | None

    def __post_init__(self) -> None:
        if self.execution_id is not None and self.lifecycle_id is not None and self.execution_id != self.lifecycle_id:
            raise ValueError("execution_id_lifecycle_id_conflict")
        if self.state not in WAL_EVENT_STATES:
            raise ValueError("unknown_wal_state")
        if type(self.event_seq) is not int or self.event_seq < 1:
            raise ValueError("event_seq_invalid")
        if type(self.expected_generation) is not int or self.expected_generation < 0:
            raise ValueError("expected_generation_invalid")
        if type(self.target_generation) is not int or self.target_generation < 0:
            raise ValueError("target_generation_invalid")
        if not isinstance(self.mutation_payload, Mapping):
            raise ValueError("mutation_payload_mapping_required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_seq": self.event_seq,
            "event_id": self.event_id,
            "operation": self.operation,
            "idempotency_key": self.idempotency_key,
            "request_digest": self.request_digest,
            "execution_id": self.execution_id,
            "lifecycle_id": self.lifecycle_id,
            "expected_generation": self.expected_generation,
            "target_generation": self.target_generation,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "state": self.state,
            "prepared_at": self.prepared_at,
            "snapshot_committed_at": self.snapshot_committed_at,
            "committed_at": self.committed_at,
            "schema_version": self.schema_version,
            "mutation_payload": copy.deepcopy(dict(self.mutation_payload)),
            "previous_committed_event_digest": self.previous_committed_event_digest,
            "result_digest": self.result_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WalEvent":
        required = (
            "event_seq", "event_id", "operation", "idempotency_key", "request_digest",
            "execution_id", "lifecycle_id", "expected_generation", "target_generation",
            "before_digest", "after_digest", "state", "prepared_at",
            "snapshot_committed_at", "committed_at", "schema_version", "mutation_payload",
            "previous_committed_event_digest", "result_digest",
        )
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(f"event_fields_missing:{','.join(missing)}")
        return cls(**{field: value[field] for field in required})


@dataclass(frozen=True)
class WalOperationResult:
    ok: bool
    status: str
    event_id: str | None = None
    event_seq: int | None = None
    state: str | None = None
    request_digest: str | None = None
    result_digest: str | None = None
    generation: int | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WalRecoveryInspection:
    status: str
    events: tuple[WalEvent, ...] = ()
    committed_events: tuple[WalEvent, ...] = ()
    pending_event: WalEvent | None = None
    snapshot_generation: int | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WalLookupResult:
    ok: bool
    status: str
    event: WalEvent | None = None
    pending: bool = False
    errors: tuple[str, ...] = ()


class TempWalLock:
    """Injectable lock abstraction; production interprocess locking is out of scope."""

    def __enter__(self) -> "TempWalLock":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def compute_request_digest(
    operation: str,
    execution_id: str | None,
    lifecycle_id: str | None,
    idempotency_key: str,
    expected_generation: int,
    mutation_payload: Mapping[str, Any],
) -> str:
    return _sha256({
        "operation": operation,
        "execution_id": execution_id,
        "lifecycle_id": lifecycle_id,
        "idempotency_key": idempotency_key,
        "expected_generation": expected_generation,
        "mutation_payload": mutation_payload,
    })


def compute_event_digest(event: WalEvent | Mapping[str, Any]) -> str:
    value = event.to_dict() if isinstance(event, WalEvent) else dict(event)
    return _sha256(value)


def compute_result_digest(result: Any) -> str:
    return _sha256(result)


def compute_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a mapping")
    value = copy.deepcopy(dict(snapshot))
    integrity = dict(value.get("integrity") or {})
    integrity.pop("snapshot_digest", None)
    value["integrity"] = integrity
    return _sha256(value)


def read_journal(storage: RegistryV2WalStorage) -> tuple[WalEvent, ...]:
    path = Path(storage.journal_path)
    if not path.exists():
        return ()
    return _parse_journal_bytes(path.read_bytes())


def repair_truncated_journal_tail_for_recovery(storage: RegistryV2WalStorage) -> bool:
    """Remove only an unterminated, non-JSON tail after a fully valid prefix."""

    path = Path(storage.journal_path)
    if not path.exists():
        return False
    raw = path.read_bytes()
    if not raw or raw.endswith(b"\n"):
        return False
    last_newline = raw.rfind(b"\n")
    if last_newline < 0:
        return False
    prefix = raw[:last_newline + 1]
    tail = raw[last_newline + 1:]
    prefix_events = _parse_journal_bytes(prefix)
    try:
        snapshot = _load_snapshot_if_present(storage)
    except ValueError as error:
        raise ValueError(f"journal_tail_repair_snapshot_invalid:{error}") from error
    prefix_inspection = _inspect_recovery_components(prefix_events, snapshot)
    if prefix_inspection.status in {SNAPSHOT_INVALID, SNAPSHOT_JOURNAL_DIVERGENCE}:
        raise ValueError(f"journal_tail_repair_not_safe:{prefix_inspection.status}")
    if prefix_inspection.pending_event is not None and snapshot is None:
        raise ValueError("journal_tail_repair_not_safe:base_snapshot_missing")
    try:
        value = json.loads(tail.decode("utf-8"), parse_constant=_reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        pass
    else:
        raise ValueError("journal_truncated_tail_complete_record")
    with path.open("r+b") as handle:
        handle.truncate(last_newline + 1)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)
    return True


def _parse_journal_bytes(raw: bytes) -> tuple[WalEvent, ...]:
    if raw and not raw.endswith(b"\n"):
        raise ValueError("journal_truncated_tail")
    events = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            raise ValueError(f"journal_blank_line:{line_number}")
        try:
            value = json.loads(line.decode("utf-8"), parse_constant=_reject_non_finite)
            if not isinstance(value, Mapping):
                raise ValueError("journal_event_mapping_required")
            events.append(WalEvent.from_dict(value))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(f"journal_line_invalid:{line_number}:{error}") from error
    _validate_journal_events(events)
    return tuple(events)


def find_committed_operation(
    journal: Iterable[WalEvent | Mapping[str, Any]],
    operation: str,
    execution_id: str | None,
    idempotency_key: str,
    request_digest: str | None = None,
) -> WalLookupResult:
    events = tuple(_coerce_event(item) for item in journal)
    matches = [
        event for event in events
        if event.state == EVENT_COMMITTED
        and event.operation == operation
        and event.execution_id == execution_id
        and event.idempotency_key == idempotency_key
    ]
    pending = [
        event for event in events
        if event.state != EVENT_COMMITTED
        and event.operation == operation
        and event.execution_id == execution_id
        and event.idempotency_key == idempotency_key
    ]
    if matches:
        digests = {event.request_digest for event in matches}
        if request_digest is not None:
            digests.add(request_digest)
        if len(digests) != 1:
            return WalLookupResult(False, WAL_CONFLICT, errors=("request_digest_conflict",))
        return WalLookupResult(True, WAL_OK, event=matches[-1])
    if pending:
        if request_digest is not None and any(event.request_digest != request_digest for event in pending):
            return WalLookupResult(False, WAL_CONFLICT, errors=("request_digest_conflict",))
        return WalLookupResult(False, WAL_RECOVERY_REQUIRED, event=pending[-1], pending=True)
    return WalLookupResult(False, WAL_NOT_FOUND)


def apply_temp_wal_mutation(
    storage: RegistryV2WalStorage,
    base_snapshot: Mapping[str, Any],
    mutation_payload: Mapping[str, Any],
    operation: str,
    execution_id: str | None,
    lifecycle_id: str | None,
    idempotency_key: str,
    expected_generation: int,
    mutation_fn: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
    *,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
    schema_version: str = "REGISTRY_EXECUTION_IDENTITY_V2_1",
) -> WalOperationResult:
    if execution_id is not None and lifecycle_id is not None and execution_id != lifecycle_id:
        return WalOperationResult(False, WAL_CONFLICT, errors=("execution_id_lifecycle_id_conflict",))
    if type(expected_generation) is not int or expected_generation < 0:
        return WalOperationResult(False, WAL_INVALID, errors=("expected_generation_invalid",))
    if not isinstance(base_snapshot, Mapping) or not isinstance(mutation_payload, Mapping):
        return WalOperationResult(False, WAL_INVALID, errors=("mapping_required",))
    request_digest = compute_request_digest(
        operation, execution_id, lifecycle_id, idempotency_key, expected_generation, mutation_payload
    )
    lock_context = lock if lock is not None else TempWalLock()
    with lock_context:
        try:
            events = read_journal(storage)
        except ValueError as error:
            return WalOperationResult(False, WAL_JOURNAL_CORRUPT, errors=(str(error),))
        lookup = find_committed_operation(events, operation, execution_id, idempotency_key, request_digest)
        if lookup.ok:
            event = lookup.event
            return WalOperationResult(True, WAL_OK, event.event_id, event.event_seq, event.state, event.request_digest, event.result_digest, event.target_generation)
        if lookup.pending:
            return WalOperationResult(False, WAL_RECOVERY_REQUIRED, errors=("recovery_required",))
        if lookup.status == WAL_CONFLICT:
            return WalOperationResult(False, WAL_CONFLICT, errors=lookup.errors)
        inspection = inspect_wal_recovery_state(storage)
        if inspection.status != CLEAN:
            return WalOperationResult(False, WAL_RECOVERY_REQUIRED, errors=(inspection.status,))
        current_snapshot = _load_snapshot_if_present(storage)
        if current_snapshot is not None:
            current_generation = _snapshot_generation(current_snapshot)
            if current_generation != expected_generation:
                return WalOperationResult(False, WAL_CONFLICT, errors=("generation_mismatch",))
            before_snapshot = current_snapshot
        else:
            before_snapshot = copy.deepcopy(dict(base_snapshot))
            if _snapshot_generation(before_snapshot) != expected_generation:
                return WalOperationResult(False, WAL_CONFLICT, errors=("generation_mismatch",))
        _fault(fault_hook, BEFORE_PREPARED)
        event_seq = _next_event_seq(events)
        event_id = f"event_{event_seq:020d}"
        before_digest = compute_snapshot_digest(before_snapshot)
        previous_digest = compute_event_digest(events[-1]) if events and events[-1].state == EVENT_COMMITTED else _last_committed_digest(events)
        prepared = _build_event(
            event_seq, event_id, operation, idempotency_key, request_digest,
            execution_id, lifecycle_id, expected_generation, expected_generation + 1,
            before_digest, None, EVENT_PREPARED, schema_version, mutation_payload,
            previous_digest, None,
        )
        _append_event(storage, prepared)
        _fault(fault_hook, AFTER_PREPARED)
        candidate = mutation_fn(copy.deepcopy(dict(before_snapshot)), copy.deepcopy(dict(mutation_payload)))
        if not isinstance(candidate, Mapping):
            return WalOperationResult(False, WAL_INVALID, event_id, event_seq, EVENT_PREPARED, request_digest, errors=("mutation_result_mapping_required",))
        witness = _materialize_snapshot(candidate, expected_generation + 1, prepared, prior_snapshot=before_snapshot)
        after_digest = witness["integrity"]["snapshot_digest"]
        _fault(fault_hook, DURING_TEMP_WRITE)
        _atomic_write_snapshot(storage, witness, fault_hook, prepared)
        _fault(fault_hook, AFTER_REPLACE)
        _fault(fault_hook, BEFORE_EVENT_COMMIT)
        result_digest = compute_result_digest({"event_id": event_id, "after_digest": after_digest, "generation": expected_generation + 1})
        committed = _build_event(
            event_seq, event_id, operation, idempotency_key, request_digest,
            execution_id, lifecycle_id, expected_generation, expected_generation + 1,
            before_digest, after_digest, EVENT_COMMITTED, schema_version, mutation_payload,
            previous_digest, result_digest,
            prepared_at=prepared.prepared_at,
        )
        _append_event(storage, committed)
        _fault(fault_hook, AFTER_EVENT_COMMIT)
        return WalOperationResult(True, WAL_OK, event_id, event_seq, EVENT_COMMITTED, request_digest, result_digest, expected_generation + 1)


def inspect_wal_recovery_state(storage: RegistryV2WalStorage) -> WalRecoveryInspection:
    try:
        events = read_journal(storage)
    except ValueError as error:
        return WalRecoveryInspection(JOURNAL_CORRUPT, errors=(str(error),))
    try:
        snapshot = _load_snapshot_if_present(storage)
    except ValueError as error:
        return WalRecoveryInspection(SNAPSHOT_INVALID, events=events, errors=(str(error),))
    return _inspect_recovery_components(events, snapshot)


def _inspect_recovery_components(
    events: tuple[WalEvent, ...] | list[WalEvent],
    snapshot: Mapping[str, Any] | None,
) -> WalRecoveryInspection:
    committed = tuple(event for event in events if event.state == EVENT_COMMITTED)
    pending = _pending_event(events)
    try:
        snapshot_generation = _snapshot_generation(snapshot) if snapshot is not None else None
    except ValueError as error:
        return WalRecoveryInspection(SNAPSHOT_INVALID, events, committed, pending, None, (str(error),))
    if snapshot is None and committed:
        return WalRecoveryInspection(SNAPSHOT_INVALID, events, committed, pending, None, ("committed_snapshot_missing",))
    if snapshot is None and pending is not None:
        return WalRecoveryInspection(SNAPSHOT_INVALID, events, committed, pending, None, ("pending_snapshot_missing",))
    if pending is None:
        if snapshot is not None and committed:
            last = committed[-1]
            if _witness_status(snapshot, last) != "valid":
                return WalRecoveryInspection(SNAPSHOT_JOURNAL_DIVERGENCE, events, committed, None, snapshot_generation, ("snapshot_witness_mismatch",))
        return WalRecoveryInspection(CLEAN, events, committed, None, snapshot_generation)
    if snapshot is not None:
        if _base_matches_pending(snapshot, pending):
            return WalRecoveryInspection(PREPARED_PENDING, events, committed, pending, snapshot_generation)
        witness_status = _witness_status(snapshot, pending)
        if witness_status == "valid":
            return WalRecoveryInspection(SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT, events, committed, pending, snapshot_generation)
        if witness_status == "incompatible":
            return WalRecoveryInspection(SNAPSHOT_JOURNAL_DIVERGENCE, events, committed, pending, snapshot_generation, ("snapshot_witness_mismatch",))
    return WalRecoveryInspection(PREPARED_PENDING, events, committed, pending, snapshot_generation)


def recover_temp_wal(
    storage: RegistryV2WalStorage,
    mutation_fn_resolver: Callable[[Mapping[str, Any]], Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None],
    *,
    lock: Any = None,
) -> WalOperationResult:
    lock_context = lock if lock is not None else TempWalLock()
    with lock_context:
        inspection = inspect_wal_recovery_state(storage)
        if inspection.status == JOURNAL_CORRUPT and "journal_truncated_tail" in inspection.errors:
            try:
                repaired = repair_truncated_journal_tail_for_recovery(storage)
            except ValueError as error:
                return WalOperationResult(False, WAL_INVALID, state=JOURNAL_CORRUPT, errors=(str(error),))
            if repaired:
                inspection = inspect_wal_recovery_state(storage)
        if inspection.status == CLEAN:
            return WalOperationResult(True, WAL_OK, state=CLEAN)
        if inspection.status in {JOURNAL_CORRUPT, SNAPSHOT_INVALID, SNAPSHOT_JOURNAL_DIVERGENCE}:
            return WalOperationResult(False, WAL_INVALID, state=inspection.status, errors=inspection.errors)
        pending = inspection.pending_event
        if pending is None:
            return WalOperationResult(False, WAL_INVALID, errors=("pending_event_missing",))
        if inspection.status == SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT:
            snapshot = _load_snapshot_if_present(storage)
            if snapshot is None:
                return WalOperationResult(False, WAL_SNAPSHOT_INVALID, errors=("witness_snapshot_missing",))
            return _finalize_pending_commit(storage, pending, _snapshot_after_digest(snapshot))
        snapshot = _load_snapshot_if_present(storage)
        if snapshot is None:
            return WalOperationResult(False, WAL_SNAPSHOT_INVALID, errors=("base_snapshot_missing",))
        if _snapshot_generation(snapshot) != pending.expected_generation:
            return WalOperationResult(False, WAL_CONFLICT, errors=("recovery_generation_mismatch",))
        if compute_snapshot_digest(snapshot) != pending.before_digest:
            return WalOperationResult(False, WAL_CONFLICT, errors=("recovery_before_digest_mismatch",))
        resolver = mutation_fn_resolver(copy.deepcopy(dict(pending.mutation_payload)))
        if resolver is None:
            return WalOperationResult(False, WAL_RECOVERY_REQUIRED, event_id=pending.event_id, event_seq=pending.event_seq, state=pending.state, errors=("mutation_resolver_required",))
        candidate = resolver(copy.deepcopy(dict(snapshot)), copy.deepcopy(dict(pending.mutation_payload)))
        if not isinstance(candidate, Mapping):
            return WalOperationResult(False, WAL_INVALID, errors=("recovery_mutation_result_mapping_required",))
        witness = _materialize_snapshot(candidate, pending.target_generation, pending, prior_snapshot=snapshot)
        if witness["integrity"]["snapshot_digest"] != pending.after_digest and pending.after_digest is not None:
            return WalOperationResult(False, WAL_CONFLICT, errors=("recovery_after_digest_mismatch",))
        _atomic_write_snapshot(storage, witness, None, pending)
        return _finalize_pending_commit(storage, pending, witness["integrity"]["snapshot_digest"])


def write_initial_snapshot(storage: RegistryV2WalStorage, snapshot: Mapping[str, Any]) -> None:
    """Write a test-owned initial witness atomically; no journal authority is created."""

    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a mapping")
    witness = copy.deepcopy(dict(snapshot))
    witness.setdefault("generation", 0)
    witness.setdefault("integrity", {})
    witness["integrity"] = dict(witness["integrity"])
    witness["integrity"]["snapshot_digest"] = compute_snapshot_digest(witness)
    _atomic_write_snapshot(storage, witness, None, None)


def _finalize_pending_commit(storage: RegistryV2WalStorage, pending: WalEvent, after_digest: str) -> WalOperationResult:
    result_digest = compute_result_digest({"event_id": pending.event_id, "after_digest": after_digest, "generation": pending.target_generation})
    committed = _build_event_from(pending, EVENT_COMMITTED, after_digest, result_digest)
    _append_event(storage, committed)
    return WalOperationResult(True, WAL_OK, committed.event_id, committed.event_seq, committed.state, committed.request_digest, committed.result_digest, committed.target_generation)


def _build_event(
    event_seq: int,
    event_id: str,
    operation: str,
    idempotency_key: str,
    request_digest: str,
    execution_id: str | None,
    lifecycle_id: str | None,
    expected_generation: int,
    target_generation: int,
    before_digest: str | None,
    after_digest: str | None,
    state: str,
    schema_version: str,
    mutation_payload: Mapping[str, Any],
    previous_committed_event_digest: str | None,
    result_digest: str | None,
    *,
    prepared_at: str | None = None,
) -> WalEvent:
    return WalEvent(
        event_seq, event_id, operation, idempotency_key, request_digest,
        execution_id, lifecycle_id, expected_generation, target_generation,
        before_digest, after_digest, state, prepared_at,
        None if state == EVENT_PREPARED else "", None if state != EVENT_COMMITTED else "",
        schema_version, copy.deepcopy(dict(mutation_payload)), previous_committed_event_digest, result_digest,
    )


def _build_event_from(event: WalEvent, state: str, after_digest: str | None, result_digest: str | None) -> WalEvent:
    return WalEvent(
        event.event_seq, event.event_id, event.operation, event.idempotency_key, event.request_digest,
        event.execution_id, event.lifecycle_id, event.expected_generation, event.target_generation,
        event.before_digest, after_digest, state, event.prepared_at,
        "" if state != EVENT_PREPARED else event.snapshot_committed_at,
        "" if state == EVENT_COMMITTED else event.committed_at,
        event.schema_version, copy.deepcopy(dict(event.mutation_payload)), event.previous_committed_event_digest, result_digest,
    )


def _materialize_snapshot(
    candidate: Mapping[str, Any],
    generation: int,
    event: WalEvent,
    *,
    prior_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = copy.deepcopy(dict(candidate))
    snapshot["generation"] = generation
    integrity = dict(snapshot.get("integrity") or {})
    prior_integrity = (prior_snapshot or {}).get("integrity") if isinstance(prior_snapshot, Mapping) else None
    if isinstance(prior_integrity, Mapping):
        integrity["last_committed_event_seq"] = prior_integrity.get("last_committed_event_seq", 0)
        integrity["last_committed_event_id"] = prior_integrity.get("last_committed_event_id")
    else:
        integrity.setdefault("last_committed_event_seq", 0)
        integrity.setdefault("last_committed_event_id", None)
    snapshot["integrity"] = integrity
    wal = dict(snapshot.get("wal") or {})
    wal.update({
        "materialized_seq": event.event_seq,
        "materialized_event_id": event.event_id,
        "materialized_request_digest": event.request_digest,
        "state": SNAPSHOT_COMMITTED,
    })
    snapshot["wal"] = wal
    integrity["snapshot_digest"] = compute_snapshot_digest(snapshot)
    return snapshot


def _atomic_write_snapshot(storage: RegistryV2WalStorage, snapshot: Mapping[str, Any], fault_hook: Callable[[str], None] | None, event: WalEvent | None) -> None:
    target = Path(storage.snapshot_path)
    parent = target.parent
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(snapshot))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fault(fault_hook, AFTER_TEMP_FSYNC)
        os.replace(temp_path, target)
        _fsync_directory(parent)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _append_event(storage: RegistryV2WalStorage, event: WalEvent) -> None:
    path = Path(storage.journal_path)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(event.to_dict()))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_snapshot_if_present(storage: RegistryV2WalStorage) -> dict[str, Any] | None:
    path = Path(storage.snapshot_path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, parse_constant=_reject_non_finite)
    if not isinstance(value, Mapping):
        raise ValueError("snapshot_mapping_required")
    snapshot = dict(value)
    integrity = snapshot.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("snapshot_digest") != compute_snapshot_digest(snapshot):
        raise ValueError("snapshot_digest_invalid")
    return snapshot


def _validate_journal_events(events: list[WalEvent]) -> None:
    if not events:
        return
    committed_digest = None
    groups: dict[tuple[int, str], list[WalEvent]] = {}
    seq_to_event_id: dict[int, str] = {}
    event_id_to_seq: dict[str, int] = {}
    last_seq = 0
    for event in events:
        if event.state not in _JOURNAL_EVENT_STATES:
            raise ValueError("journal_operational_state_invalid")
        expected_request_digest = compute_request_digest(
            event.operation,
            event.execution_id,
            event.lifecycle_id,
            event.idempotency_key,
            event.expected_generation,
            event.mutation_payload,
        )
        if event.request_digest != expected_request_digest:
            raise ValueError("request_digest_invalid")
        if event.target_generation != event.expected_generation + 1:
            raise ValueError("target_generation_invalid")
        if event.state == EVENT_PREPARED:
            if event.after_digest is not None or event.result_digest is not None:
                raise ValueError("prepared_result_fields_invalid")
        else:
            if not isinstance(event.after_digest, str) or not event.after_digest:
                raise ValueError("committed_after_digest_invalid")
            expected_result_digest = compute_result_digest({
                "event_id": event.event_id,
                "after_digest": event.after_digest,
                "generation": event.target_generation,
            })
            if event.result_digest != expected_result_digest:
                raise ValueError("committed_result_digest_invalid")
        prior_event_id = seq_to_event_id.setdefault(event.event_seq, event.event_id)
        prior_event_seq = event_id_to_seq.setdefault(event.event_id, event.event_seq)
        if prior_event_id != event.event_id or prior_event_seq != event.event_seq:
            raise ValueError("event_identity_global_conflict")
        if event.event_seq < last_seq:
            raise ValueError("event_seq_not_monotonic")
        last_seq = event.event_seq
        groups.setdefault((event.event_seq, event.event_id), []).append(event)
        if event.previous_committed_event_digest != committed_digest:
            raise ValueError("event_chain_pointer_invalid")
        if event.state == EVENT_COMMITTED:
            committed_digest = compute_event_digest(event)
    for group in groups.values():
        if not any(event.state == EVENT_PREPARED for event in group):
            raise ValueError("event_committed_without_prepared")
        identity_fields = (
            "event_seq", "event_id", "operation", "idempotency_key", "request_digest",
            "execution_id", "lifecycle_id", "expected_generation", "target_generation",
            "before_digest", "previous_committed_event_digest", "schema_version",
        )
        first = group[0]
        if any(getattr(event, field) != getattr(first, field) for event in group for field in identity_fields):
            raise ValueError("event_identity_conflict")
        request_digests = {event.request_digest for event in group}
        if len(request_digests) != 1:
            raise ValueError("duplicate_event_request_digest_conflict")
        states = [event.state for event in group]
        if states.count(EVENT_COMMITTED) > 1:
            raise ValueError("duplicate_event_state")
        if states.count(EVENT_PREPARED) == len(states):
            if len({compute_event_digest(event) for event in group}) != 1:
                raise ValueError("duplicate_prepared_event_conflict")
            continue
        order = {EVENT_PREPARED: 0, EVENT_COMMITTED: 1}
        if [order[state] for state in states] != sorted(order[state] for state in states):
            raise ValueError("event_state_transition_order_invalid")


def _pending_event(events: Iterable[WalEvent]) -> WalEvent | None:
    groups: dict[tuple[int, str], list[WalEvent]] = {}
    for event in events:
        groups.setdefault((event.event_seq, event.event_id), []).append(event)
    for group in groups.values():
        states = {event.state for event in group}
        if EVENT_COMMITTED not in states and EVENT_PREPARED in states:
            return group[-1]
    return None


def _coerce_event(value: WalEvent | Mapping[str, Any]) -> WalEvent:
    return value if isinstance(value, WalEvent) else WalEvent.from_dict(value)


def _next_event_seq(events: Iterable[WalEvent]) -> int:
    return max((event.event_seq for event in events), default=0) + 1


def _last_committed_digest(events: Iterable[WalEvent]) -> str | None:
    committed = [event for event in events if event.state == EVENT_COMMITTED]
    return compute_event_digest(committed[-1]) if committed else None


def _snapshot_generation(snapshot: Mapping[str, Any]) -> int:
    generation = snapshot.get("generation")
    if type(generation) is not int or generation < 0:
        raise ValueError("snapshot_generation_invalid")
    return generation


def _snapshot_event_id(snapshot: Mapping[str, Any]) -> Any:
    return (snapshot.get("wal") or {}).get("materialized_event_id")


def _snapshot_event_seq(snapshot: Mapping[str, Any]) -> Any:
    return (snapshot.get("wal") or {}).get("materialized_seq")


def _snapshot_after_digest(snapshot: Mapping[str, Any]) -> str:
    integrity = snapshot.get("integrity")
    if not isinstance(integrity, Mapping) or not isinstance(integrity.get("snapshot_digest"), str):
        raise ValueError("snapshot_digest_invalid")
    digest = integrity["snapshot_digest"]
    if digest != compute_snapshot_digest(snapshot):
        raise ValueError("snapshot_digest_invalid")
    return digest


def _base_matches_pending(snapshot: Mapping[str, Any], pending: WalEvent) -> bool:
    try:
        return (
            _snapshot_generation(snapshot) == pending.expected_generation
            and compute_snapshot_digest(snapshot) == pending.before_digest
        )
    except (TypeError, ValueError):
        return False


def _witness_status(snapshot: Mapping[str, Any], event: WalEvent) -> str:
    wal = snapshot.get("wal")
    if not isinstance(wal, Mapping):
        return "base"
    has_witness = (
        wal.get("state") == SNAPSHOT_COMMITTED
        or (wal.get("materialized_seq") is not None and wal.get("materialized_seq") != 0)
        or wal.get("materialized_event_id") is not None
        or wal.get("materialized_request_digest") is not None
    )
    if not has_witness:
        return "base"
    try:
        after_digest = _snapshot_after_digest(snapshot)
    except ValueError:
        return "incompatible"
    matches = (
        wal.get("state") == SNAPSHOT_COMMITTED
        and wal.get("materialized_seq") == event.event_seq
        and wal.get("materialized_event_id") == event.event_id
        and wal.get("materialized_request_digest") == event.request_digest
        and _snapshot_generation(snapshot) == event.target_generation
    )
    if event.state == EVENT_COMMITTED:
        matches = matches and event.after_digest == after_digest
    return "valid" if matches else "incompatible"


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non_finite_json:{value}")


def _fault(fault_hook: Callable[[str], None] | None, stage: str) -> None:
    if fault_hook is not None:
        fault_hook(stage)


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except (AttributeError, OSError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


__all__ = (
    "AFTER_EVENT_COMMIT",
    "AFTER_PREPARED",
    "AFTER_REPLACE",
    "AFTER_TEMP_FSYNC",
    "BEFORE_EVENT_COMMIT",
    "BEFORE_PREPARED",
    "CLEAN",
    "DURING_TEMP_WRITE",
    "EVENT_COMMITTED",
    "EVENT_PREPARED",
    "JOURNAL_CORRUPT",
    "PREPARED_PENDING",
    "SNAPSHOT_COMMITTED",
    "SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT",
    "SNAPSHOT_INVALID",
    "SNAPSHOT_JOURNAL_DIVERGENCE",
    "TempWalLock",
    "WalEvent",
    "WalLookupResult",
    "WalOperationResult",
    "WalRecoveryInspection",
    "RegistryV2WalStorage",
    "WAL_CONFLICT",
    "WAL_INVALID",
    "WAL_JOURNAL_CORRUPT",
    "WAL_NOT_FOUND",
    "WAL_OK",
    "WAL_RECOVERY_REQUIRED",
    "WAL_SNAPSHOT_INVALID",
    "WAL_EVENT_STATES",
    "apply_temp_wal_mutation",
    "canonical_json",
    "canonical_json_bytes",
    "compute_event_digest",
    "compute_request_digest",
    "compute_result_digest",
    "compute_snapshot_digest",
    "find_committed_operation",
    "inspect_wal_recovery_state",
    "read_journal",
    "repair_truncated_journal_tail_for_recovery",
    "recover_temp_wal",
    "write_initial_snapshot",
)
