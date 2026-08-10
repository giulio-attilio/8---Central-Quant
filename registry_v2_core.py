"""Temporary-only V2 register/update/close/reconciliation core.

The module is intentionally dormant and has no production path.  Every
operation receives an explicitly injected :class:`RegistryV2WalStorage` and
delegates durable mutation to the V2.4 WAL engine.  Rows are selected only by
their physical ``execution_id``; logical grouping fields are never selectors.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from numbers import Real
from typing import Any

import registry_execution_schema as schema
import registry_v2_reader as reader
import registry_v2_wal as wal


REGISTER = "REGISTER"
UPDATE = "UPDATE"
PARTIAL_CLOSE = "PARTIAL_CLOSE"
FULL_CLOSE = "FULL_CLOSE"
RECONCILIATION = "RECONCILIATION"
RECONCILIATION_PENDING = "PENDING"
RECONCILIATION_RECONCILED = "RECONCILED"
_RECONCILIATION_STATUSES = frozenset({RECONCILIATION_PENDING, RECONCILIATION_RECONCILED})

CORE_EXTERNAL_BLOCKED = "REGISTRY_V2_CORE_EXTERNAL_BLOCKED"
CORE_IDENTITY_INVALID = "REGISTRY_V2_CORE_IDENTITY_INVALID"
CORE_EXPECTED_IDENTITY_MISMATCH = "REGISTRY_EXPECTED_IDENTITY_MISMATCH"
CORE_PATCH_INVALID = "REGISTRY_V2_CORE_PATCH_INVALID"
CORE_STATE_CONFLICT = "REGISTRY_V2_CORE_STATE_CONFLICT"

_CLOSED_STATES = {schema.CLOSED_PROVISIONAL, schema.CLOSED_RECONCILED}
_STATE_RANK = {
    schema.ENTRY_INTENT: 0,
    schema.ENTRY_PENDING_RECONCILIATION: 1,
    schema.OPEN: 2,
    schema.PARTIALLY_CLOSED: 3,
    schema.CLOSE_PENDING_RECONCILIATION: 4,
    schema.CLOSED_PROVISIONAL: 5,
    schema.CLOSED_RECONCILED: 6,
    schema.QUARANTINED: 7,
}
_IMMUTABLE_UPDATE_FIELDS = frozenset({
    "execution_id",
    "lifecycle_id",
    "logical_trade_id",
    "owner_type",
    "bot",
    "setup",
    "symbol",
    "side",
    "execution_mode",
    "registry_mode",
    "signal_id",
    "decision_id",
    "execution_provenance",
    "provenance",
    "source_mode",
    "mode_source",
    "execution_mode_source",
    "registry_mode_source",
})
_STRONG_ID_FIELDS = ("client_order_id", "broker_order_id", "exchange_order_id", "fill_id")
_UPDATE_CLOSE_ONLY_FIELDS = frozenset({
    "remaining_qty",
    "closed_qty",
    "close_events",
    "last_close_event_id",
    "exit_qty",
    "close_event_id",
    "close_reason",
    "close_evidence",
    "close_event",
    "close_facts",
    "quantity",
    "entry_qty",
    "filled_qty",
    "closed_quantity",
    "remaining_quantity",
    "exit_quantity",
    "economics",
    "factual_economics",
    "fee",
    "fees",
    "funding",
    "funding_fee",
    "gross_pnl",
    "net_pnl",
    "realized_pnl",
    "realized_r",
    "exit_price",
    "pnl_pct",
    "reconciliation_status",
})


def register_trade_v2(
    storage: wal.RegistryV2WalStorage,
    trade: Mapping[str, Any],
    idempotency_key: str,
    expected_generation: int,
    *,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
) -> wal.WalOperationResult:
    """Register one canonical CENTRAL execution through the V2.4 WAL."""

    if not isinstance(trade, Mapping):
        return _invalid("trade_mapping_required")
    row = copy.deepcopy(dict(trade))
    execution_id = row.get("execution_id")
    lifecycle_id = row.get("lifecycle_id")
    identity_error = _validate_execution_pair(execution_id, lifecycle_id)
    if identity_error:
        return identity_error
    validation = schema.validate_registry_execution_row(row)
    if not validation.ok:
        return wal.WalOperationResult(
            False,
            validation.status,
            errors=tuple(validation.errors or (validation.status,)),
        )
    if row.get("owner_type") != schema.CENTRAL:
        return _external_blocked()
    payload = {"trade": row}

    def builder(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(dict(snapshot))
        open_trades = dict(candidate["open_trades"])
        closed_trades = dict(candidate["closed_trades"])
        if execution_id in open_trades or execution_id in closed_trades:
            raise _CoreError(wal.WAL_CONFLICT, ("execution_id_exists",))
        open_trades[execution_id] = copy.deepcopy(row)
        candidate["open_trades"] = open_trades
        candidate["closed_trades"] = closed_trades
        return _rebuild_candidate(candidate)

    return _execute_operation(
        storage,
        REGISTER,
        execution_id,
        idempotency_key,
        expected_generation,
        payload,
        builder,
        fault_hook=fault_hook,
        lock=lock,
    )


def update_trade_v2(
    storage: wal.RegistryV2WalStorage,
    execution_id: str,
    lifecycle_id: str,
    patch: Mapping[str, Any],
    idempotency_key: str,
    expected_generation: int,
    *,
    expected_identity: Mapping[str, Any] | None = None,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
) -> wal.WalOperationResult:
    """Update one execution selected exclusively by exact execution ID."""

    identity_error = _validate_execution_pair(execution_id, lifecycle_id)
    if identity_error:
        return identity_error
    if not isinstance(patch, Mapping):
        return _invalid("patch_mapping_required")
    patch_copy = copy.deepcopy(dict(patch))
    if not _json_safe(patch_copy):
        return _invalid("patch_not_json_serializable")
    expected_identity_value, expected_identity_error = _prepare_expected_identity(expected_identity)
    if expected_identity_error is not None:
        return expected_identity_error
    payload = {"execution_id": execution_id, "patch": patch_copy}
    if expected_identity_value is not None:
        payload["expected_identity"] = expected_identity_value

    def builder(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        collection, current = _locate_execution(snapshot, execution_id)
        if current is None:
            raise _CoreError(wal.WAL_NOT_FOUND, ("execution_id_not_found",))
        if current.get("owner_type") != schema.CENTRAL:
            raise _CoreError(CORE_EXTERNAL_BLOCKED, ("owner_type",))
        _assert_expected_identity(execution_id, current, expected_identity_value)
        for field in _IMMUTABLE_UPDATE_FIELDS:
            if field in patch_copy and patch_copy[field] != current.get(field):
                raise _CoreError(CORE_PATCH_INVALID, (f"immutable_field:{field}",))
        for field in _STRONG_ID_FIELDS:
            if field in patch_copy and not _strong_patch_is_allowed(current.get(field), patch_copy[field]):
                raise _CoreError(CORE_PATCH_INVALID, (f"strong_id_replacement:{field}",))
        close_fields = sorted(_UPDATE_CLOSE_ONLY_FIELDS.intersection(patch_copy))
        if close_fields:
            raise _CoreError(CORE_PATCH_INVALID, tuple(f"close_only_field:{field}" for field in close_fields))
        candidate_row = copy.deepcopy(dict(current))
        candidate_row.update(copy.deepcopy(patch_copy))
        current_state = current.get("lifecycle_state")
        next_state = candidate_row.get("lifecycle_state")
        if next_state != current_state and (
            next_state in _CLOSED_STATES
            or next_state in {schema.PARTIALLY_CLOSED, schema.CLOSE_PENDING_RECONCILIATION}
            or current_state in _CLOSED_STATES
        ):
            raise _CoreError(CORE_STATE_CONFLICT, ("update_cannot_close_or_reopen",))
        if _STATE_RANK.get(next_state, -1) < _STATE_RANK.get(current_state, -1):
            raise _CoreError(CORE_STATE_CONFLICT, ("lifecycle_state_regression",))
        candidate = copy.deepcopy(dict(snapshot))
        if collection == "open_trades":
            candidate["open_trades"][execution_id] = candidate_row
        else:
            candidate["closed_trades"][execution_id] = candidate_row
        return _rebuild_candidate(candidate)

    return _execute_operation(
        storage,
        UPDATE,
        execution_id,
        idempotency_key,
        expected_generation,
        payload,
        builder,
        expected_identity=expected_identity_value,
        fault_hook=fault_hook,
        lock=lock,
    )


def partial_close_trade_v2(
    storage: wal.RegistryV2WalStorage,
    execution_id: str,
    lifecycle_id: str,
    close_event_id: str,
    closed_qty: Any,
    idempotency_key: str,
    expected_generation: int,
    *,
    remaining_qty: Any = None,
    factual_economics: Mapping[str, Any] | None = None,
    expected_identity: Mapping[str, Any] | None = None,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
    **aliases: Any,
) -> wal.WalOperationResult:
    """Apply a factual partial close while keeping positive remainder open."""

    identity_error = _validate_execution_pair(execution_id, lifecycle_id)
    if identity_error:
        return identity_error
    if not _nonempty_string(close_event_id):
        return _invalid("close_event_id_required")
    if closed_qty is None:
        closed_qty = aliases.pop("quantity_closed", aliases.pop("quantity", None))
    if remaining_qty is None and "remaining" in aliases:
        remaining_qty = aliases.pop("remaining")
    if factual_economics is None and "economics" in aliases:
        factual_economics = aliases.pop("economics")
    if aliases:
        return _invalid(*(f"unknown_argument:{key}" for key in sorted(aliases)))
    if factual_economics is not None and not isinstance(factual_economics, Mapping):
        return _invalid("factual_economics_mapping_required")
    expected_identity_value, expected_identity_error = _prepare_expected_identity(expected_identity)
    if expected_identity_error is not None:
        return expected_identity_error
    try:
        closed_value = _quantity(closed_qty)
    except ValueError as error:
        return _invalid(str(error))
    if closed_value <= 0:
        return _invalid("closed_qty_must_be_positive")
    requested_remaining = None
    if remaining_qty is not None:
        try:
            requested_remaining = _quantity(remaining_qty)
        except ValueError as error:
            return _invalid(str(error))
    economics = copy.deepcopy(dict(factual_economics or {}))
    if not _json_safe(economics):
        return _invalid("factual_economics_not_json_serializable")
    close_facts = {
        "close_event_id": close_event_id,
        "closed_qty": _json_number(closed_value),
        "remaining_qty": _json_number(requested_remaining) if requested_remaining is not None else None,
        "factual_economics": economics,
        "kind": "PARTIAL_CLOSE",
    }
    close_digest = wal.compute_result_digest(close_facts)
    payload = {"close": close_facts, "close_event_digest": close_digest}
    if expected_identity_value is not None:
        payload["expected_identity"] = expected_identity_value

    def replay(snapshot: Mapping[str, Any], events: tuple[wal.WalEvent, ...], request_digest: str) -> wal.WalOperationResult | None:
        return _special_close_replay(snapshot, events, execution_id, close_event_id, close_digest, PARTIAL_CLOSE)

    def builder(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        collection, current = _locate_execution(snapshot, execution_id)
        if current is None:
            raise _CoreError(wal.WAL_NOT_FOUND, ("execution_id_not_found",))
        if current.get("owner_type") != schema.CENTRAL:
            raise _CoreError(CORE_EXTERNAL_BLOCKED, ("owner_type",))
        _assert_expected_identity(execution_id, current, expected_identity_value)
        if collection != "open_trades":
            raise _CoreError(wal.WAL_CONFLICT, ("closed_trade_partial_close_conflict",))
        current_remaining = _row_remaining(current)
        next_remaining = requested_remaining if requested_remaining is not None else current_remaining - closed_value
        if next_remaining <= 0:
            raise _CoreError(wal.WAL_CONFLICT, ("partial_close_requires_positive_remaining",))
        if next_remaining >= current_remaining or closed_value > current_remaining:
            raise _CoreError(wal.WAL_CONFLICT, ("partial_close_overclose_or_non_decreasing",))
        if requested_remaining is not None and current_remaining - closed_value != next_remaining:
            raise _CoreError(wal.WAL_CONFLICT, ("partial_close_quantity_mismatch",))
        candidate = copy.deepcopy(dict(snapshot))
        row = copy.deepcopy(dict(current))
        row["remaining_qty"] = _json_number(next_remaining)
        row["closed_qty"] = _json_number(_quantity(row.get("closed_qty", 0)) + closed_value)
        row["lifecycle_state"] = schema.PARTIALLY_CLOSED
        _append_close_fact(row, close_facts)
        _merge_economics(row, economics)
        candidate["open_trades"][execution_id] = row
        return _rebuild_candidate(candidate)

    return _execute_operation(
        storage,
        PARTIAL_CLOSE,
        execution_id,
        idempotency_key,
        expected_generation,
        payload,
        builder,
        committed_validator=_validate_committed_close_event,
        expected_identity=expected_identity_value,
        special_replay=replay,
        fault_hook=fault_hook,
        lock=lock,
    )


def close_trade_v2(
    storage: wal.RegistryV2WalStorage,
    execution_id: str,
    lifecycle_id: str,
    close_event_id: str,
    idempotency_key: str,
    expected_generation: int,
    *,
    remaining_qty: Any = 0,
    factual_economics: Mapping[str, Any] | None = None,
    broker_evidence: Mapping[str, Any] | None = None,
    expected_identity: Mapping[str, Any] | None = None,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
) -> wal.WalOperationResult:
    """Record factual zero remainder and close only to the justified state."""

    identity_error = _validate_execution_pair(execution_id, lifecycle_id)
    if identity_error:
        return identity_error
    if not _nonempty_string(close_event_id):
        return _invalid("close_event_id_required")
    if factual_economics is not None and not isinstance(factual_economics, Mapping):
        return _invalid("factual_economics_mapping_required")
    if broker_evidence is not None and not isinstance(broker_evidence, Mapping):
        return _invalid("broker_evidence_mapping_required")
    expected_identity_value, expected_identity_error = _prepare_expected_identity(expected_identity)
    if expected_identity_error is not None:
        return expected_identity_error
    try:
        factual_remaining = _quantity(remaining_qty)
    except ValueError as error:
        return _invalid(str(error))
    if factual_remaining < 0:
        return _invalid("remaining_qty_must_not_be_negative")
    evidence = copy.deepcopy(dict(broker_evidence or {}))
    economics_input = copy.deepcopy(dict(factual_economics or {}))
    evidence_status, evidence_status_error = _extract_reconciliation_status(evidence)
    economics_status, economics_status_error = _extract_reconciliation_status(economics_input)
    if evidence_status_error or economics_status_error:
        return _invalid(evidence_status_error or economics_status_error or "reconciliation_status_invalid")
    if evidence_status is not None and economics_status is not None and evidence_status != economics_status:
        return _invalid("reconciliation_status_conflict")
    reconciliation_status = evidence_status or economics_status
    economics = _economics_only(economics_input)
    if not _json_safe(evidence):
        return _invalid("broker_evidence_not_json_serializable")
    if not _json_safe(economics):
        return _invalid("factual_economics_not_json_serializable")
    if factual_remaining != 0:
        evidence_remaining = _evidence_remaining(evidence)
        if evidence_remaining != 0:
            return _invalid("full_close_requires_zero_remaining")
        factual_remaining = Decimal("0")
    close_facts = {
        "close_event_id": close_event_id,
        "remaining_qty": _json_number(factual_remaining),
        "factual_economics": economics,
        "broker_evidence": evidence,
        "kind": "FULL_CLOSE",
    }
    if reconciliation_status is not None:
        close_facts["reconciliation_status"] = reconciliation_status
    close_digest = wal.compute_result_digest(close_facts)
    payload = {"close": close_facts, "close_event_digest": close_digest}
    if expected_identity_value is not None:
        payload["expected_identity"] = expected_identity_value

    def replay(snapshot: Mapping[str, Any], events: tuple[wal.WalEvent, ...], request_digest: str) -> wal.WalOperationResult | None:
        return _special_close_replay(snapshot, events, execution_id, close_event_id, close_digest, FULL_CLOSE)

    def builder(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        collection, current = _locate_execution(snapshot, execution_id)
        if current is None:
            raise _CoreError(wal.WAL_NOT_FOUND, ("execution_id_not_found",))
        if current.get("owner_type") != schema.CENTRAL:
            raise _CoreError(CORE_EXTERNAL_BLOCKED, ("owner_type",))
        _assert_expected_identity(execution_id, current, expected_identity_value)
        if collection != "open_trades":
            raise _CoreError(wal.WAL_CONFLICT, ("closed_trade_full_close_conflict",))
        current_remaining = _row_remaining(current)
        if current_remaining <= 0:
            raise _CoreError(wal.WAL_CONFLICT, ("remaining_qty_already_zero",))
        candidate = copy.deepcopy(dict(snapshot))
        row = copy.deepcopy(dict(current))
        row["remaining_qty"] = 0
        _append_close_fact(row, close_facts)
        _merge_economics(row, economics)
        _materialize_reconciliation_status(row, reconciliation_status)
        if evidence:
            row["broker_evidence"] = copy.deepcopy(evidence)
        next_state = _full_close_state(reconciliation_status, economics)
        row["lifecycle_state"] = next_state
        if next_state in _CLOSED_STATES:
            candidate["open_trades"].pop(execution_id, None)
            candidate["closed_trades"][execution_id] = row
        else:
            candidate["open_trades"][execution_id] = row
        return _rebuild_candidate(candidate)

    return _execute_operation(
        storage,
        FULL_CLOSE,
        execution_id,
        idempotency_key,
        expected_generation,
        payload,
        builder,
        committed_validator=_validate_committed_close_event,
        expected_identity=expected_identity_value,
        special_replay=replay,
        state_validator=lambda snapshot, events: _assert_full_close_request_state_coherence(
            snapshot, events, execution_id,
        ),
        fault_hook=fault_hook,
        lock=lock,
    )


def reconcile_trade_v2(
    storage: wal.RegistryV2WalStorage,
    execution_id: str,
    lifecycle_id: str,
    evidence: Mapping[str, Any],
    idempotency_key: str,
    expected_generation: int,
    *,
    expected_identity: Mapping[str, Any] | None = None,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
) -> wal.WalOperationResult:
    """Apply late fee/funding evidence without reopening a trade."""

    identity_error = _validate_execution_pair(execution_id, lifecycle_id)
    if identity_error:
        return identity_error
    if not isinstance(evidence, Mapping):
        return _invalid("evidence_mapping_required")
    evidence_copy = copy.deepcopy(dict(evidence))
    if not _json_safe(evidence_copy):
        return _invalid("evidence_not_json_serializable")
    reconciliation_status, status_error = _extract_reconciliation_status(evidence_copy)
    if status_error:
        return _invalid(status_error)
    expected_identity_value, expected_identity_error = _prepare_expected_identity(expected_identity)
    if expected_identity_error is not None:
        return expected_identity_error
    evidence_digest = wal.compute_result_digest(evidence_copy)
    payload = {"evidence": evidence_copy, "evidence_digest": evidence_digest}
    if expected_identity_value is not None:
        payload["expected_identity"] = expected_identity_value

    def replay(snapshot: Mapping[str, Any], events: tuple[wal.WalEvent, ...], request_digest: str) -> wal.WalOperationResult | None:
        return _special_reconciliation_replay(snapshot, events, execution_id, evidence_digest)

    def builder(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        collection, current = _locate_execution(snapshot, execution_id)
        if current is None:
            raise _CoreError(wal.WAL_NOT_FOUND, ("execution_id_not_found",))
        if current.get("owner_type") != schema.CENTRAL:
            raise _CoreError(CORE_EXTERNAL_BLOCKED, ("owner_type",))
        _assert_expected_identity(execution_id, current, expected_identity_value)
        candidate = copy.deepcopy(dict(snapshot))
        row = copy.deepcopy(dict(current))
        _merge_economics(row, evidence_copy)
        _materialize_reconciliation_status(row, reconciliation_status)
        row["last_reconciliation_evidence_digest"] = evidence_digest
        next_state = _reconciliation_next_state(row, reconciliation_status)
        row["lifecycle_state"] = next_state
        if collection == "open_trades" and next_state in _CLOSED_STATES:
            candidate["open_trades"].pop(execution_id, None)
            candidate["closed_trades"][execution_id] = row
        elif collection == "open_trades":
            candidate["open_trades"][execution_id] = row
        else:
            candidate["closed_trades"][execution_id] = row
        return _rebuild_candidate(candidate)

    return _execute_operation(
        storage,
        RECONCILIATION,
        execution_id,
        idempotency_key,
        expected_generation,
        payload,
        builder,
        committed_validator=_validate_committed_reconciliation_event,
        expected_identity=expected_identity_value,
        special_replay=replay,
        state_validator=lambda snapshot, events: _assert_reconciliation_state_coherence(
            snapshot, events, execution_id, reconciliation_status,
        ),
        fault_hook=fault_hook,
        lock=lock,
    )


reconcile_trade = reconcile_trade_v2
reconcile_execution_v2 = reconcile_trade_v2


class _CoreError(ValueError):
    def __init__(self, status: str, errors: tuple[str, ...]):
        super().__init__(";".join(errors))
        self.status = status
        self.errors = errors


def _execute_operation(
    storage: wal.RegistryV2WalStorage,
    operation: str,
    execution_id: str,
    idempotency_key: str,
    expected_generation: int,
    payload: Mapping[str, Any],
    builder: Callable[[Mapping[str, Any]], dict[str, Any]],
    *,
    committed_validator: Callable[[Mapping[str, Any], tuple[wal.WalEvent, ...], wal.WalEvent], None] | None = None,
    expected_identity: Mapping[str, Any] | None = None,
    special_replay: Callable[[Mapping[str, Any], tuple[wal.WalEvent, ...], str], wal.WalOperationResult | None] | None = None,
    state_validator: Callable[[Mapping[str, Any], tuple[wal.WalEvent, ...]], None] | None = None,
    fault_hook: Callable[[str], None] | None = None,
    lock: Any = None,
    _lock_held: bool = False,
) -> wal.WalOperationResult:
    request_error = _validate_request_args(idempotency_key, expected_generation)
    if request_error:
        return request_error
    if not isinstance(storage, wal.RegistryV2WalStorage):
        return _invalid("storage_backend_required")
    if not _json_safe(payload):
        return _invalid("mutation_payload_not_json_serializable")
    if lock is not None and not _lock_held:
        with lock:
            return _execute_operation(
                storage,
                operation,
                execution_id,
                idempotency_key,
                expected_generation,
                payload,
                builder,
                committed_validator=committed_validator,
                expected_identity=expected_identity,
                special_replay=special_replay,
                state_validator=state_validator,
                fault_hook=fault_hook,
                lock=None,
                _lock_held=True,
            )
    try:
        request_digest = wal.compute_request_digest(
            operation,
            execution_id,
            execution_id,
            idempotency_key,
            expected_generation,
            payload,
        )
        events = wal.read_journal(storage)
    except (TypeError, ValueError) as error:
        return _invalid(f"journal_or_request_invalid:{error}")
    try:
        snapshot, exists = _load_snapshot_or_empty(storage)
    except _CoreError as error:
        return _operation_error(error)
    if events and not exists:
        return _invalid("snapshot_missing_after_durable_event")
    try:
        _validate_snapshot_journal_coherence(snapshot, events)
        if state_validator is not None:
            state_validator(snapshot, events)
    except _CoreError as error:
        return _operation_error(error)
    if expected_identity is not None:
        try:
            _collection, current = _locate_execution(snapshot, execution_id)
            if current is not None:
                _assert_expected_identity(execution_id, current, expected_identity)
        except _CoreError as error:
            return _operation_error(error)
    lookup = wal.find_committed_operation(events, operation, execution_id, idempotency_key, request_digest)
    if lookup.ok and lookup.event is not None and committed_validator is not None:
        try:
            committed_validator(snapshot, events, lookup.event)
        except _CoreError as error:
            return _operation_error(error)
    early = _lookup_result(lookup)
    if early is not None:
        return early
    if special_replay is not None:
        try:
            replayed = special_replay(snapshot, events, request_digest)
        except _CoreError as error:
            return _operation_error(error)
        if replayed is not None:
            return replayed
    if snapshot.get("generation") != expected_generation:
        return _conflict("generation_mismatch")
    try:
        candidate = builder(copy.deepcopy(snapshot))
        _validate_candidate(candidate)
    except _CoreError as error:
        return _operation_error(error)
    except (TypeError, ValueError, KeyError) as error:
        return _invalid(f"candidate_invalid:{error}")

    def mutation_fn(current: Mapping[str, Any], _mutation_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return builder(current)

    try:
        return wal.apply_temp_wal_mutation(
            storage,
            snapshot,
            payload,
            operation,
            execution_id,
            execution_id,
            idempotency_key,
            expected_generation,
            mutation_fn,
            fault_hook=fault_hook,
            lock=lock,
        )
    except (TypeError, ValueError, KeyError) as error:
        return _invalid(f"wal_mutation_invalid:{error}")


def _validate_snapshot_journal_coherence(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
) -> None:
    """Fail closed when the snapshot witness cannot be reconciled with WAL."""

    if not events:
        return
    if not isinstance(snapshot, Mapping):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("snapshot_mapping_required",))
    try:
        snapshot_digests = _snapshot_digest_candidates(snapshot)
    except (TypeError, ValueError) as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"snapshot_digest_uncomputable:{error}",)) from error
    committed = [event for event in events if event.state == wal.EVENT_COMMITTED]
    committed_ids = {(event.event_seq, event.event_id) for event in committed}
    pending_groups: dict[tuple[int, str], wal.WalEvent] = {}
    for event in events:
        logical_id = (event.event_seq, event.event_id)
        if event.state == wal.EVENT_PREPARED and logical_id not in committed_ids:
            pending_groups.setdefault(logical_id, event)
    pending = tuple(pending_groups.values())
    if len(pending) > 1:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("multiple_pending_events",))
    latest = committed[-1] if committed else None
    pending_event = pending[0] if pending else None
    wal_meta = snapshot.get("wal")
    if not isinstance(wal_meta, Mapping):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("snapshot_wal_mapping_required",))
    generation = snapshot.get("generation")
    if type(generation) is not int or generation < 0:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("snapshot_generation_invalid",))

    def require_materialized(event: wal.WalEvent) -> None:
        if (
            generation != event.target_generation
            or wal_meta.get("materialized_seq") != event.event_seq
            or wal_meta.get("materialized_event_id") != event.event_id
            or wal_meta.get("materialized_request_digest") != event.request_digest
            or wal_meta.get("state") != wal.SNAPSHOT_COMMITTED
        ):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("snapshot_materialization_mismatch",))

    if pending_event is not None:
        if generation == pending_event.expected_generation:
            if pending_event.before_digest not in snapshot_digests:
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("pending_before_digest_mismatch",))
            if latest is None:
                if (
                    wal_meta.get("materialized_seq") != 0
                    or wal_meta.get("materialized_event_id") is not None
                    or wal_meta.get("materialized_request_digest") is not None
                ):
                    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("pending_base_materialization_mismatch",))
            else:
                require_materialized(latest)
            return
        if generation == pending_event.target_generation:
            require_materialized(pending_event)
            return
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("pending_generation_mismatch",))

    if latest is None:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("journal_event_state_unrecognized",))
    require_materialized(latest)
    if latest.after_digest not in snapshot_digests:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("snapshot_after_digest_mismatch",))


def _snapshot_digest_candidates(snapshot: Mapping[str, Any]) -> frozenset[str]:
    """Return material digests with the disposable operation ledger ignored."""

    raw_digest = wal.compute_snapshot_digest(snapshot)
    normalized = copy.deepcopy(dict(snapshot))
    normalized["operation_ledger"] = {}
    normalized_digest = wal.compute_snapshot_digest(normalized)
    return frozenset((raw_digest, normalized_digest))


def _load_snapshot_or_empty(storage: wal.RegistryV2WalStorage) -> tuple[dict[str, Any], bool]:
    path = storage.snapshot_path
    if not path.exists():
        return _empty_snapshot(), False
    result = reader.read_registry_v2(path)
    if result.ok and result.document is not None:
        return copy.deepcopy(dict(result.document)), True
    if result.document is None or "operation_ledger" not in result.errors:
        raise _CoreError(wal.WAL_SNAPSHOT_INVALID, result.errors or (result.status,))
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, Mapping) or "operation_ledger" in raw:
            raise ValueError("operation_ledger_fallback_not_applicable")
        integrity = raw.get("integrity")
        if not isinstance(integrity, Mapping) or integrity.get("snapshot_digest") != wal.compute_snapshot_digest(raw):
            raise ValueError("snapshot_digest_invalid")
        return copy.deepcopy(dict(raw)), True
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise _CoreError(wal.WAL_SNAPSHOT_INVALID, (f"operation_ledger_optional_cache_invalid:{error}",)) from error


def _empty_snapshot() -> dict[str, Any]:
    indexes = reader.project_indexes_for_json(schema.build_registry_v2_indexes([]))
    document = {
        "schema_version": schema.SCHEMA_VERSION,
        "registry_version": schema.REGISTRY_VERSION,
        "generation": 0,
        "snapshot_id": "v2-core-temporary",
        "updated_at": "1970-01-01T00:00:00Z",
        "integrity": {
            "snapshot_digest": "placeholder",
            "last_committed_event_seq": 0,
            "last_committed_event_id": None,
        },
        "wal": {
            "materialized_seq": 0,
            "materialized_event_id": None,
            "materialized_request_digest": None,
            "state": "CLEAN",
        },
        "open_trades": {},
        "closed_trades": {},
        "external_observations": {},
        "indexes": indexes,
        "operation_ledger": {},
        "migration": {
            "phase": "V2_CORE_TEMPORARY",
            "source_snapshot_digest": None,
            "journal_cursor": 0,
        },
    }
    document["integrity"]["snapshot_digest"] = reader.compute_registry_v2_snapshot_digest(document)
    return document


def _rebuild_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(candidate))
    result.setdefault("operation_ledger", {})
    rows = _canonical_index_rows(result)
    try:
        rebuilt = schema.build_registry_v2_indexes(rows)
        indexes = reader.project_indexes_for_json(rebuilt)
        indexes.update(_build_unique_indexes(rows))
    except (TypeError, ValueError, KeyError) as error:
        raise _CoreError(wal.WAL_CONFLICT, (f"index_conflict:{error}",)) from error
    result["indexes"] = indexes
    return result


def _validate_candidate(candidate: Mapping[str, Any]) -> None:
    required = (
        "schema_version", "registry_version", "generation", "snapshot_id", "updated_at",
        "integrity", "wal", "open_trades", "closed_trades", "external_observations",
        "indexes", "operation_ledger", "migration",
    )
    missing = tuple(field for field in required if field not in candidate)
    if missing:
        raise _CoreError(wal.WAL_INVALID, tuple(f"missing:{field}" for field in missing))
    if candidate["schema_version"] != schema.SCHEMA_VERSION or candidate["registry_version"] != schema.REGISTRY_VERSION:
        raise _CoreError(wal.WAL_INVALID, ("schema_version",))
    if type(candidate["generation"]) is not int or candidate["generation"] < 0:
        raise _CoreError(wal.WAL_INVALID, ("generation",))
    if not isinstance(candidate["open_trades"], Mapping) or not isinstance(candidate["closed_trades"], Mapping):
        raise _CoreError(wal.WAL_INVALID, ("trade_collections_mapping_required",))
    for collection_name, collection, open_collection in (
        ("open_trades", candidate["open_trades"], True),
        ("closed_trades", candidate["closed_trades"], False),
    ):
        for execution_key, row in collection.items():
            if not isinstance(row, Mapping) or row.get("execution_id") != execution_key:
                raise _CoreError(wal.WAL_CONFLICT, (f"{collection_name}_execution_identity_invalid",))
            validation = schema.validate_registry_execution_row(row)
            if not validation.ok:
                raise _CoreError(wal.WAL_INVALID, tuple(validation.errors or (validation.status,)))
            state = row.get("lifecycle_state")
            if open_collection and state in _CLOSED_STATES:
                raise _CoreError(wal.WAL_CONFLICT, ("closed_state_in_open_trades",))
            if not open_collection and state not in _CLOSED_STATES:
                raise _CoreError(wal.WAL_CONFLICT, ("open_state_in_closed_trades",))
    rows = _canonical_index_rows(candidate)
    try:
        expected = reader.project_indexes_for_json(schema.build_registry_v2_indexes(rows))
    except (TypeError, ValueError, KeyError) as error:
        raise _CoreError(wal.WAL_CONFLICT, (f"index_rebuild:{error}",)) from error
    persisted = candidate.get("indexes")
    if not isinstance(persisted, Mapping) or any(persisted.get(name) != value for name, value in expected.items()):
        raise _CoreError(wal.WAL_CONFLICT, ("persisted_indexes_mismatch",))
    _build_unique_indexes(rows)


def _canonical_index_rows(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the persisted index sequence for a canonical V2 snapshot.

    The schema deliberately preserves the sequence it receives for non-unique
    index members.  Snapshot JSON is canonicalized by key, so the core must
    provide the same sequence before persistence and after reload: all OPEN
    rows by execution ID, followed by all CLOSED rows by execution ID.
    """

    open_trades = snapshot["open_trades"]
    closed_trades = snapshot["closed_trades"]
    if not isinstance(open_trades, Mapping) or not isinstance(closed_trades, Mapping):
        raise TypeError("trade_collections_mapping_required")
    return [
        *(open_trades[execution_id] for execution_id in sorted(open_trades)),
        *(closed_trades[execution_id] for execution_id in sorted(closed_trades)),
    ]


def _build_unique_indexes(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    indexes: dict[str, dict[str, str]] = {
        "by_client_order_id": {},
        "by_broker_order_id": {},
        "by_exchange_order_id": {},
        "by_fill_id": {},
        "by_close_event_id": {},
    }
    for row in rows:
        execution_id = row["execution_id"]
        for field in _STRONG_ID_FIELDS:
            name = f"by_{field}"
            for value in _strong_values(row, field):
                previous = indexes[name].get(value)
                if previous is not None and previous != execution_id:
                    raise ValueError(f"{field}_collision:{value}")
                indexes[name][value] = execution_id
        for close_event in _row_close_events(row):
            close_event_id = close_event.get("close_event_id")
            if not _nonempty_string(close_event_id):
                raise ValueError("close_event_id_invalid")
            key = f"{execution_id}|{close_event_id}"
            previous = indexes["by_close_event_id"].get(key)
            if previous is not None:
                raise ValueError(f"close_event_collision:{key}")
            indexes["by_close_event_id"][key] = execution_id
    return indexes


def _locate_execution(snapshot: Mapping[str, Any], execution_id: str) -> tuple[str | None, Mapping[str, Any] | None]:
    open_row = snapshot["open_trades"].get(execution_id)
    closed_row = snapshot["closed_trades"].get(execution_id)
    if open_row is not None and closed_row is not None:
        raise _CoreError(wal.WAL_CONFLICT, ("execution_id_in_open_and_closed",))
    if open_row is not None:
        return "open_trades", open_row
    if closed_row is not None:
        return "closed_trades", closed_row
    return None, None


def _prepare_expected_identity(
    expected_identity: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, wal.WalOperationResult | None]:
    if expected_identity is None:
        return None, None
    if not isinstance(expected_identity, Mapping):
        return None, _invalid("expected_identity_mapping_required")
    value = copy.deepcopy(dict(expected_identity))
    allowed = {
        "execution_id",
        "lifecycle_id",
        "logical_trade_id",
        "owner_type",
        "bot",
        "setup",
        "symbol",
        "side",
        *_STRONG_ID_FIELDS,
    }
    unknown = tuple(sorted(set(value) - allowed))
    if unknown:
        return None, _invalid(*(f"expected_identity_field_unknown:{field}" for field in unknown))
    if not _json_safe(value):
        return None, _invalid("expected_identity_not_json_serializable")
    return value, None


def _assert_expected_identity(
    execution_id: str,
    row: Mapping[str, Any],
    expected_identity: Mapping[str, Any] | None,
) -> None:
    if expected_identity is None:
        return
    expected_execution_id = expected_identity.get("execution_id", execution_id)
    expected_lifecycle_id = expected_identity.get("lifecycle_id", execution_id)
    if (
        expected_execution_id != execution_id
        or row.get("execution_id") != execution_id
        or expected_lifecycle_id != execution_id
        or row.get("lifecycle_id") != execution_id
    ):
        raise _CoreError(CORE_EXPECTED_IDENTITY_MISMATCH, ("execution_id_lifecycle_id",))
    for field, expected_value in expected_identity.items():
        if field in {"execution_id", "lifecycle_id"}:
            continue
        if not _identity_value_matches(row.get(field), expected_value):
            raise _CoreError(CORE_EXPECTED_IDENTITY_MISMATCH, (field,))


def _identity_value_matches(actual: Any, expected: Any) -> bool:
    if not _identity_value_present(actual) or not _identity_value_present(expected):
        return False
    actual_values = _identity_values(actual)
    expected_values = _identity_values(expected)
    if actual_values is not None or expected_values is not None:
        if actual_values is None:
            return actual in expected_values
        if expected_values is None:
            return expected in actual_values
        return all(value in actual_values for value in expected_values)
    return actual == expected


def _identity_values(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(item for item in value if isinstance(item, str) and item.strip())
    return None


def _identity_value_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(_identity_values(value))
    return value is not None


def _strong_patch_is_allowed(current: Any, proposed: Any) -> bool:
    if not _identity_value_present(proposed):
        return False
    if not _identity_value_present(current):
        return True
    current_values = _identity_values(current)
    proposed_values = _identity_values(proposed)
    if current_values is not None and proposed_values is not None:
        return all(value in proposed_values for value in current_values)
    if current_values is not None:
        return len(current_values) == 1 and proposed == current_values[0]
    if proposed_values is not None:
        return current in proposed_values
    return current == proposed


def _validate_committed_close_event(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    event: wal.WalEvent,
) -> None:
    if event.state != wal.EVENT_COMMITTED or event.operation not in {PARTIAL_CLOSE, FULL_CLOSE}:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("committed_close_event_invalid",))
    payload = event.mutation_payload
    close = payload.get("close") if isinstance(payload, Mapping) else None
    digest = payload.get("close_event_digest") if isinstance(payload, Mapping) else None
    if not isinstance(close, Mapping) or not isinstance(digest, str):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("journal_close_payload_invalid",))
    try:
        if wal.compute_result_digest(close) != digest:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("journal_close_digest_invalid",))
    except (TypeError, ValueError) as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"journal_close_payload_invalid:{error}",)) from error
    _assert_close_replay_row_coherence(snapshot, events, event, close)


def _validate_committed_reconciliation_event(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    event: wal.WalEvent,
) -> None:
    if event.state != wal.EVENT_COMMITTED or event.operation != RECONCILIATION:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("committed_reconciliation_event_invalid",))
    payload = event.mutation_payload
    evidence = payload.get("evidence") if isinstance(payload, Mapping) else None
    digest = payload.get("evidence_digest") if isinstance(payload, Mapping) else None
    if not isinstance(evidence, Mapping) or not isinstance(digest, str):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("journal_evidence_payload_invalid",))
    try:
        if wal.compute_result_digest(evidence) != digest:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("journal_evidence_digest_invalid",))
    except (TypeError, ValueError) as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"journal_evidence_payload_invalid:{error}",)) from error
    _assert_reconciliation_row_coherence(snapshot, events, event, evidence)


def _special_close_replay(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    execution_id: str,
    close_event_id: str,
    close_digest: str,
    operation: str,
) -> wal.WalOperationResult | None:
    committed_matches: list[wal.WalEvent] = []
    close_operations = {PARTIAL_CLOSE, FULL_CLOSE}
    for event in events:
        if (
            event.state != wal.EVENT_COMMITTED
            or event.execution_id != execution_id
            or event.operation not in close_operations
        ):
            continue
        payload = event.mutation_payload
        close = payload.get("close") if isinstance(payload, Mapping) else None
        if not isinstance(close, Mapping) or close.get("close_event_id") != close_event_id:
            continue
        event_digest = payload.get("close_event_digest")
        if event.operation != operation or event_digest != close_digest:
            raise _CoreError(wal.WAL_CONFLICT, ("close_event_digest_conflict",))
        _validate_committed_close_event(snapshot, events, event)
        committed_matches.append(event)
    if committed_matches:
        return _result_from_event(committed_matches[0])

    record = _find_close_record(snapshot, execution_id, close_event_id)
    if record is None:
        return None
    record_digest = _close_record_digest(record)
    if record_digest != close_digest:
        raise _CoreError(wal.WAL_CONFLICT, ("close_event_digest_conflict",))
    raise _CoreError(wal.WAL_RECOVERY_REQUIRED, ("close_event_record_without_committed_event",))


def _special_reconciliation_replay(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    execution_id: str,
    evidence_digest: str,
) -> wal.WalOperationResult | None:
    for event in events:
        if event.state != wal.EVENT_COMMITTED or event.operation != RECONCILIATION or event.execution_id != execution_id:
            continue
        payload = event.mutation_payload
        if not isinstance(payload, Mapping) or payload.get("evidence_digest") != evidence_digest:
            continue
        evidence = payload.get("evidence")
        if not isinstance(evidence, Mapping):
            raise _CoreError(wal.WAL_INVALID, ("journal_evidence_payload_invalid",))
        _validate_committed_reconciliation_event(snapshot, events, event)
        return _result_from_event(event)

    records = snapshot.get("operation_ledger", {}).get("reconciliation_events", {}).get(execution_id, {})
    record = records.get(evidence_digest) if isinstance(records, Mapping) else None
    row_has_digest = any(
        row.get("execution_id") == execution_id
        and row.get("last_reconciliation_evidence_digest") == evidence_digest
        for row in list(snapshot.get("open_trades", {}).values()) + list(snapshot.get("closed_trades", {}).values())
        if isinstance(row, Mapping)
    )
    if record is not None or row_has_digest:
        raise _CoreError(wal.WAL_RECOVERY_REQUIRED, ("evidence_record_without_committed_event",))
    return None


def _extract_reconciliation_status(values: Mapping[str, Any]) -> tuple[str | None, str | None]:
    if "reconciliation_status" not in values:
        return None, None
    status = values.get("reconciliation_status")
    if not isinstance(status, str) or status not in _RECONCILIATION_STATUSES:
        return None, "reconciliation_status_invalid"
    return status, None


def _economics_only(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in values.items()
        if key != "reconciliation_status"
    }


def _full_close_state(status: str | None, economics: Mapping[str, Any]) -> str:
    if status == RECONCILIATION_RECONCILED:
        return schema.CLOSED_RECONCILED
    if economics:
        return schema.CLOSED_PROVISIONAL
    return schema.CLOSE_PENDING_RECONCILIATION


def _materialize_reconciliation_status(row: dict[str, Any], status: str | None) -> None:
    if status is None or row.get("reconciliation_status") == RECONCILIATION_RECONCILED:
        return
    row["reconciliation_status"] = status


def _reconciliation_next_state(row: Mapping[str, Any], status: str | None) -> str:
    current_state = row.get("lifecycle_state")
    effective_status = status or row.get("reconciliation_status")
    if current_state == schema.CLOSE_PENDING_RECONCILIATION:
        return (
            schema.CLOSED_RECONCILED
            if effective_status == RECONCILIATION_RECONCILED
            else schema.CLOSED_PROVISIONAL
        )
    if current_state == schema.CLOSED_PROVISIONAL and effective_status == RECONCILIATION_RECONCILED:
        return schema.CLOSED_RECONCILED
    return current_state


def _journal_reconciliation_status(values: Mapping[str, Any]) -> str | None:
    status, error = _extract_reconciliation_status(values)
    if error is not None:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (error,))
    return status


def _expected_full_close_state(
    events: tuple[wal.WalEvent, ...],
    full_event: wal.WalEvent,
) -> str:
    payload = full_event.mutation_payload
    close = payload.get("close") if isinstance(payload, Mapping) else None
    if not isinstance(close, Mapping):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_payload_missing",))
    factual_economics = close.get("factual_economics")
    if not isinstance(factual_economics, Mapping):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_economics_missing",))
    expected = _full_close_state(_journal_reconciliation_status(close), _economics_only(factual_economics))
    later_reconciliations = sorted(
        (
            candidate
            for candidate in events
            if candidate.state == wal.EVENT_COMMITTED
            and candidate.operation == RECONCILIATION
            and candidate.execution_id == full_event.execution_id
            and candidate.event_seq > full_event.event_seq
        ),
        key=lambda candidate: candidate.event_seq,
    )
    for candidate in later_reconciliations:
        payload = candidate.mutation_payload
        evidence = payload.get("evidence") if isinstance(payload, Mapping) else None
        if not isinstance(evidence, Mapping):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_payload_missing",))
        status = _journal_reconciliation_status(evidence)
        if expected != schema.CLOSED_RECONCILED:
            expected = (
                schema.CLOSED_RECONCILED
                if status == RECONCILIATION_RECONCILED
                else schema.CLOSED_PROVISIONAL
            )
    return expected


def _assert_full_close_request_state_coherence(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    execution_id: str,
) -> None:
    try:
        _collection, row = _locate_execution(snapshot, execution_id)
    except _CoreError as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, error.errors) from error
    if row is None:
        return
    has_full_close = any(
        candidate.state == wal.EVENT_COMMITTED
        and candidate.operation == FULL_CLOSE
        and candidate.execution_id == execution_id
        for candidate in events
    )
    if not has_full_close and row.get("reconciliation_status") in _RECONCILIATION_STATUSES:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_status_without_full_close",))


def _assert_reconciliation_state_coherence(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    execution_id: str,
    incoming_status: str | None = None,
) -> None:
    try:
        collection, row = _locate_execution(snapshot, execution_id)
    except _CoreError as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, error.errors) from error
    if row is None:
        if any(
            candidate.state == wal.EVENT_COMMITTED
            and candidate.execution_id == execution_id
            and candidate.operation in {FULL_CLOSE, RECONCILIATION}
            for candidate in events
        ):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_execution_missing",))
        return
    full_closes = sorted(
        (
            candidate
            for candidate in events
            if candidate.state == wal.EVENT_COMMITTED
            and candidate.operation == FULL_CLOSE
            and candidate.execution_id == execution_id
        ),
        key=lambda candidate: candidate.event_seq,
    )
    if not full_closes:
        if row.get("reconciliation_status") in _RECONCILIATION_STATUSES and row.get("lifecycle_state") in {
            schema.ENTRY_INTENT,
            schema.ENTRY_PENDING_RECONCILIATION,
            schema.OPEN,
            schema.PARTIALLY_CLOSED,
        }:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_status_without_full_close",))
        if incoming_status is not None and row.get("lifecycle_state") in {
            schema.ENTRY_INTENT,
            schema.ENTRY_PENDING_RECONCILIATION,
            schema.OPEN,
            schema.PARTIALLY_CLOSED,
        }:
            raise _CoreError(CORE_STATE_CONFLICT, ("reconciliation_status_requires_full_close",))
        if collection != "open_trades" or row.get("lifecycle_state") in _CLOSED_STATES | {schema.CLOSE_PENDING_RECONCILIATION}:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_state_without_full_close",))
        return
    if len(full_closes) != 1:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("multiple_full_close_events",))
    full_event = full_closes[0]
    payload = full_event.mutation_payload
    close = payload.get("close") if isinstance(payload, Mapping) else None
    if not isinstance(close, Mapping):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_payload_missing",))
    _assert_close_replay_row_coherence(snapshot, events, full_event, close)


def _assert_close_replay_row_coherence(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    event: wal.WalEvent,
    close: Mapping[str, Any],
) -> None:
    try:
        collection, row = _locate_execution(snapshot, event.execution_id)
    except _CoreError as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, error.errors) from error
    if row is None:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_execution_missing",))
    close_event_id = close.get("close_event_id")
    committed_closes = sorted(
        (
            candidate
            for candidate in events
            if candidate.state == wal.EVENT_COMMITTED
            and candidate.execution_id == event.execution_id
            and candidate.operation in {PARTIAL_CLOSE, FULL_CLOSE}
        ),
        key=lambda candidate: candidate.event_seq,
    )
    if not any(candidate.event_id == event.event_id for candidate in committed_closes):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_event_not_in_committed_chain",))
    row_facts = _row_close_events(row)
    row_facts_by_id = {fact.get("close_event_id"): fact for fact in row_facts}
    for candidate in committed_closes:
        payload = candidate.mutation_payload
        candidate_close = payload.get("close") if isinstance(payload, Mapping) else None
        if not isinstance(candidate_close, Mapping):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_payload_missing",))
        candidate_id = candidate_close.get("close_event_id")
        row_fact = row_facts_by_id.get(candidate_id)
        if row_fact is None:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_fact_missing",))
        try:
            if wal.compute_result_digest(candidate_close) != payload.get("close_event_digest"):
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("journal_close_digest_invalid",))
            if wal.compute_result_digest(row_fact) != payload.get("close_event_digest"):
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_fact_digest_mismatch",))
        except (TypeError, ValueError) as error:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"close_fact_uncomputable:{error}",)) from error

    expected_remaining, has_full_close = _reconstruct_close_chain(row, committed_closes)
    _assert_execution_economics_coherence(snapshot, events, event.execution_id)

    later_full_close = any(
        candidate.operation == FULL_CLOSE and candidate.event_seq > event.event_seq
        for candidate in committed_closes
    )
    if event.operation == PARTIAL_CLOSE and later_full_close:
        full_event = next(
            candidate
            for candidate in committed_closes
            if candidate.operation == FULL_CLOSE and candidate.event_seq > event.event_seq
        )
        expected_state = _expected_full_close_state(events, full_event)
        _assert_full_close_row_state(row, collection, expected_state)
        if _row_remaining(row) != 0:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("historical_full_close_remaining_nonzero",))
        return

    if event.operation == PARTIAL_CLOSE:
        if collection != "open_trades" or row.get("lifecycle_state") in _CLOSED_STATES:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_row_not_open",))
        current_remaining = _row_remaining(row)
        if current_remaining <= 0:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_remaining_invalid",))
        if expected_remaining is not None and current_remaining != expected_remaining:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_row_quantity_mismatch",))
        return

    if event.operation == FULL_CLOSE:
        expected_state = _expected_full_close_state(events, event)
        _assert_full_close_row_state(row, collection, expected_state)
        if _row_remaining(row) != 0:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("full_close_remaining_nonzero",))
        if has_full_close and expected_remaining is not None and expected_remaining != Decimal("0"):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("full_close_chain_remaining_mismatch",))
        return
    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_operation_invalid",))


def _assert_full_close_row_state(
    row: Mapping[str, Any],
    collection: str | None,
    expected_state: str,
) -> None:
    actual_state = row.get("lifecycle_state")
    if expected_state == schema.CLOSE_PENDING_RECONCILIATION:
        if collection != "open_trades" or actual_state != schema.CLOSE_PENDING_RECONCILIATION:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("full_close_row_not_pending_reconciliation",))
    elif collection != "closed_trades" or actual_state != expected_state:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("full_close_row_state_mismatch",))
    materialized_status = row.get("reconciliation_status")
    if actual_state == schema.CLOSED_RECONCILED and materialized_status != RECONCILIATION_RECONCILED:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciled_status_missing",))
    if actual_state != schema.CLOSED_RECONCILED and materialized_status == RECONCILIATION_RECONCILED:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciled_status_state_mismatch",))


def _reconstruct_close_chain(
    row: Mapping[str, Any],
    committed_closes: list[wal.WalEvent],
) -> tuple[Decimal | None, bool]:
    partials: list[tuple[wal.WalEvent, Mapping[str, Any], Decimal, Decimal | None]] = []
    has_full_close = False
    try:
        for event in committed_closes:
            payload = event.mutation_payload
            close = payload.get("close") if isinstance(payload, Mapping) else None
            if not isinstance(close, Mapping):
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("close_payload_missing",))
            if event.operation == PARTIAL_CLOSE:
                if has_full_close:
                    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_after_full_close",))
                closed_qty = _quantity(close.get("closed_qty"))
                if closed_qty <= 0:
                    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_closed_qty_invalid",))
                explicit = close.get("remaining_qty")
                explicit_remaining = _quantity(explicit) if explicit is not None else None
                if explicit_remaining is not None and explicit_remaining <= 0:
                    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_remaining_invalid",))
                partials.append((event, close, closed_qty, explicit_remaining))
            elif event.operation == FULL_CLOSE:
                if has_full_close:
                    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("duplicate_full_close",))
                full_remaining = close.get("remaining_qty")
                if full_remaining is not None and _quantity(full_remaining) != 0:
                    raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("full_close_remaining_invalid",))
                has_full_close = True
        quantity = row.get("quantity")
        initial_remaining: Decimal | None = _quantity(quantity) if quantity is not None else None
        if initial_remaining is not None and initial_remaining <= 0:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("initial_quantity_invalid",))
        if initial_remaining is None:
            first_explicit = next(
                (index for index, (_event, _close, _closed, explicit) in enumerate(partials) if explicit is not None),
                None,
            )
            if first_explicit is not None:
                initial_remaining = sum(
                    (closed for _event, _close, closed, _explicit in partials[: first_explicit + 1]),
                    _quantity("0"),
                ) + partials[first_explicit][3]
        expected = initial_remaining
        for _event, _close, closed_qty, explicit_remaining in partials:
            if expected is None:
                continue
            next_remaining = expected - closed_qty
            if next_remaining <= 0:
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_chain_invalid",))
            if explicit_remaining is not None and explicit_remaining != next_remaining:
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("partial_close_remaining_mismatch",))
            expected = next_remaining
        if has_full_close and expected is not None:
            if expected <= 0:
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("full_close_chain_before_zero",))
            expected = Decimal("0")
        return expected, has_full_close
    except _CoreError:
        raise
    except (TypeError, ValueError, InvalidOperation) as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"close_chain_invalid:{error}",)) from error


def _assert_execution_economics_coherence(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    execution_id: str,
) -> None:
    try:
        _collection, row = _locate_execution(snapshot, execution_id)
    except _CoreError as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, error.errors) from error
    if row is None:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("economics_execution_missing",))
    factual_events = sorted(
        (
            candidate
            for candidate in events
            if candidate.state == wal.EVENT_COMMITTED
            and candidate.execution_id == execution_id
            and candidate.operation in {PARTIAL_CLOSE, FULL_CLOSE, RECONCILIATION}
        ),
        key=lambda candidate: candidate.event_seq,
    )
    expected_economics: dict[str, Any] = {}
    for candidate in factual_events:
        payload = candidate.mutation_payload
        if not isinstance(payload, Mapping):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("factual_event_payload_missing",))
        if candidate.operation in {PARTIAL_CLOSE, FULL_CLOSE}:
            source = payload.get("close")
            digest = payload.get("close_event_digest")
            field_name = "close"
            values = source.get("factual_economics") if isinstance(source, Mapping) else None
        else:
            source = payload.get("evidence")
            digest = payload.get("evidence_digest")
            field_name = "reconciliation"
            values = source
        if not isinstance(source, Mapping) or not isinstance(values, Mapping):
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"{field_name}_economics_missing",))
        _journal_reconciliation_status(source)
        try:
            if wal.compute_result_digest(source) != digest:
                raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"{field_name}_journal_digest_invalid",))
        except (TypeError, ValueError) as error:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"{field_name}_payload_invalid:{error}",)) from error
        expected_economics.update(_economics_only(values))
    economics = row.get("factual_economics")
    canonical_economics = row.get("economics")
    if not expected_economics:
        return
    if not isinstance(economics, Mapping) or not isinstance(canonical_economics, Mapping):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconstructed_economics_missing",))
    for field, value in expected_economics.items():
        if economics.get(field) != value or canonical_economics.get(field) != value:
            raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, (f"reconstructed_economics_mismatch:{field}",))


def _assert_reconciliation_row_coherence(
    snapshot: Mapping[str, Any],
    events: tuple[wal.WalEvent, ...],
    event: wal.WalEvent,
    evidence: Mapping[str, Any],
) -> None:
    try:
        collection, row = _locate_execution(snapshot, event.execution_id)
    except _CoreError as error:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, error.errors) from error
    if row is None:
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_execution_missing",))
    _assert_reconciliation_state_coherence(snapshot, events, event.execution_id)
    reconciliations = tuple(
        candidate
        for candidate in events
        if candidate.state == wal.EVENT_COMMITTED
        and candidate.operation == RECONCILIATION
        and candidate.execution_id == event.execution_id
    )
    if not any(candidate.event_id == event.event_id for candidate in reconciliations):
        raise _CoreError(wal.SNAPSHOT_JOURNAL_DIVERGENCE, ("reconciliation_not_in_committed_chain",))
    _assert_execution_economics_coherence(snapshot, events, event.execution_id)


def _result_from_event(event: wal.WalEvent) -> wal.WalOperationResult:
    return wal.WalOperationResult(
        True,
        wal.WAL_OK,
        event.event_id,
        event.event_seq,
        event.state,
        event.request_digest,
        event.result_digest,
        event.target_generation,
    )


def _close_record_digest(record: Mapping[str, Any]) -> str | None:
    value = record.get("evidence_digest")
    if isinstance(value, str):
        return value
    try:
        return wal.compute_result_digest(record)
    except (TypeError, ValueError):
        return None


def _find_close_record(snapshot: Mapping[str, Any], execution_id: str, close_event_id: str) -> Mapping[str, Any] | None:
    ledger = snapshot.get("operation_ledger", {})
    if isinstance(ledger, Mapping):
        records = ledger.get("close_events", {})
        if isinstance(records, Mapping):
            by_execution = records.get(execution_id, {})
            if isinstance(by_execution, Mapping) and isinstance(by_execution.get(close_event_id), Mapping):
                return by_execution[close_event_id]
    for row in list(snapshot.get("open_trades", {}).values()) + list(snapshot.get("closed_trades", {}).values()):
        if row.get("execution_id") != execution_id:
            continue
        for event in _row_close_events(row):
            if event.get("close_event_id") == close_event_id:
                return event
    return None


def _append_close_fact(row: dict[str, Any], close_facts: Mapping[str, Any]) -> None:
    events = list(_row_close_events(row))
    events.append(copy.deepcopy(dict(close_facts)))
    row["close_events"] = events
    row["last_close_event_id"] = close_facts["close_event_id"]


def _row_close_events(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = row.get("close_events", [])
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _merge_economics(row: dict[str, Any], values: Mapping[str, Any]) -> None:
    if not values:
        return
    economics_values = _economics_only(values)
    if not economics_values:
        return
    economics = dict(row.get("economics") or {})
    economics.update(copy.deepcopy(economics_values))
    row["economics"] = economics
    factual = dict(row.get("factual_economics") or {})
    factual.update(copy.deepcopy(economics_values))
    row["factual_economics"] = factual
    for key in ("fee", "fees", "funding", "funding_fee"):
        if key in economics_values:
            row[key] = copy.deepcopy(economics_values[key])


def _row_remaining(row: Mapping[str, Any]) -> Decimal:
    value = row.get("remaining_qty", row.get("quantity"))
    try:
        return _quantity(value)
    except ValueError as error:
        raise _CoreError(wal.WAL_INVALID, (f"remaining_qty_invalid:{error}",)) from error


def _evidence_remaining(evidence: Mapping[str, Any]) -> Decimal | None:
    for key in ("remaining_qty", "broker_remaining_qty", "position_qty", "position_size"):
        if key in evidence:
            try:
                return _quantity(evidence[key])
            except ValueError:
                return None
    return None


def _quantity(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("quantity_required")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("quantity_finite_required")
        return value
    if isinstance(value, Real):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("quantity_finite_required")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("quantity_invalid") from error
    raise ValueError("quantity_numeric_required")


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _validate_execution_pair(execution_id: Any, lifecycle_id: Any) -> wal.WalOperationResult | None:
    if not _nonempty_string(execution_id):
        return _invalid("execution_id_required")
    if not _nonempty_string(lifecycle_id):
        return _invalid("lifecycle_id_required")
    if execution_id != lifecycle_id:
        return _conflict("execution_id_lifecycle_id_mismatch")
    return None


def _validate_request_args(idempotency_key: Any, expected_generation: Any) -> wal.WalOperationResult | None:
    if not _nonempty_string(idempotency_key):
        return _invalid("idempotency_key_required")
    if type(expected_generation) is not int or expected_generation < 0:
        return _invalid("expected_generation_invalid")
    return None


def _lookup_result(lookup: wal.WalLookupResult) -> wal.WalOperationResult | None:
    if lookup.ok and lookup.event is not None:
        event = lookup.event
        return wal.WalOperationResult(
            True,
            wal.WAL_OK,
            event.event_id,
            event.event_seq,
            event.state,
            event.request_digest,
            event.result_digest,
            event.target_generation,
        )
    if lookup.pending:
        return wal.WalOperationResult(False, wal.WAL_RECOVERY_REQUIRED, errors=("recovery_required",))
    if lookup.status == wal.WAL_CONFLICT:
        return _conflict(*(lookup.errors or ("request_digest_conflict",)))
    return None


def _operation_error(error: _CoreError) -> wal.WalOperationResult:
    return wal.WalOperationResult(False, error.status, errors=error.errors)


def _invalid(*errors: str) -> wal.WalOperationResult:
    return wal.WalOperationResult(False, wal.WAL_INVALID, errors=tuple(errors))


def _conflict(*errors: str) -> wal.WalOperationResult:
    return wal.WalOperationResult(False, wal.WAL_CONFLICT, errors=tuple(errors))


def _external_blocked() -> wal.WalOperationResult:
    return wal.WalOperationResult(False, CORE_EXTERNAL_BLOCKED, errors=("MANUAL_EXTERNAL",))


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strong_values(row: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = row.get(field)
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(item for item in value if isinstance(item, str) and item.strip())
    return ()


def _json_safe(value: Any) -> bool:
    try:
        wal.canonical_json(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


__all__ = (
    "CORE_EXTERNAL_BLOCKED",
    "CORE_EXPECTED_IDENTITY_MISMATCH",
    "CORE_IDENTITY_INVALID",
    "CORE_PATCH_INVALID",
    "CORE_STATE_CONFLICT",
    "FULL_CLOSE",
    "PARTIAL_CLOSE",
    "RECONCILIATION",
    "RECONCILIATION_PENDING",
    "RECONCILIATION_RECONCILED",
    "REGISTER",
    "UPDATE",
    "close_trade_v2",
    "reconcile_execution_v2",
    "reconcile_trade",
    "reconcile_trade_v2",
    "register_trade_v2",
    "partial_close_trade_v2",
    "update_trade_v2",
)
