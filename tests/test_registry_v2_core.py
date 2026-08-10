from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

import registry_execution_schema as schema
import registry_v2_core as core
import registry_v2_reader as reader
import registry_v2_wal as wal


class CrashInjected(RuntimeError):
    pass


def _storage(tmp_path: Path) -> wal.RegistryV2WalStorage:
    return wal.RegistryV2WalStorage(
        snapshot_path=tmp_path / "snapshot.json",
        journal_path=tmp_path / "events.jsonl",
        lock_path=tmp_path / "lock",
        backup_dir=tmp_path / "backups",
    )


def _row(execution_id: str = "exec-1", **overrides):
    row = {
        "execution_id": execution_id,
        "lifecycle_id": execution_id,
        "logical_trade_id": "FALCON:FALCON15:BTCUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "owner_type": schema.CENTRAL,
        "execution_mode": schema.PAPER,
        "registry_mode": schema.PAPER,
        "lifecycle_state": schema.OPEN,
        "execution_provenance": {"source": "v2-core-test"},
        "signal_id": f"signal-{execution_id}",
        "decision_id": f"decision-{execution_id}",
        "position_side": "LONG",
        "metadata": {},
        "quantity": 10,
        "remaining_qty": 10,
    }
    row.update(overrides)
    return row


def _new_storage(tmp_path: Path) -> wal.RegistryV2WalStorage:
    tmp_path.mkdir(parents=True, exist_ok=True)
    storage = _storage(tmp_path)
    wal.write_initial_snapshot(storage, core._empty_snapshot())
    return storage


def _document(storage):
    result = reader.read_registry_v2(storage.snapshot_path)
    assert result.ok, result.errors
    assert result.document is not None
    return result.document


def _raw_document(storage):
    return json.loads(storage.snapshot_path.read_text(encoding="utf-8"))


def _generation(storage) -> int:
    return _document(storage)["generation"]


def _register(storage, row, key="register"):
    return core.register_trade_v2(storage, row, key, _generation(storage))


def _events(storage):
    return wal.read_journal(storage)


def _rewrite_document(storage, mutate):
    document = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    mutate(document)
    document["integrity"]["snapshot_digest"] = wal.compute_snapshot_digest(document)
    storage.snapshot_path.write_text(wal.canonical_json(document) + "\n", encoding="utf-8")


def _raise_at(stage):
    def hook(current):
        if current == stage:
            raise CrashInjected(stage)
    return hook


def test_register_materializes_open_trade_and_wal_authority(tmp_path):
    storage = _new_storage(tmp_path)
    result = _register(storage, _row())

    assert result.ok is True
    assert result.status == wal.WAL_OK
    assert result.state == wal.EVENT_COMMITTED
    document = _document(storage)
    assert document["generation"] == 1
    assert document["open_trades"]["exec-1"]["execution_id"] == "exec-1"
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]


def test_register_allows_repeated_logical_trade_id_but_not_execution_id(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row("exec-1"), "k1").ok
    second = _register(storage, _row("exec-2", signal_id="signal-2", decision_id="decision-2"), "k2")
    duplicate = core.register_trade_v2(storage, _row(), "k3", _generation(storage))

    assert second.ok is True
    assert duplicate.status == wal.WAL_CONFLICT
    assert set(_document(storage)["open_trades"]) == {"exec-1", "exec-2"}


_CANONICAL_LOW = "exec_00000000-0000-4000-8000-000000000001"
_CANONICAL_HIGH = "exec_00000000-0000-4000-8000-000000000002"


def _register_same_logical_pair(storage, insertion_order):
    for index, execution_id in enumerate(insertion_order, 1):
        result = _register(storage, _row(execution_id), f"same-logical-register-{index}")
        assert result.ok is True
    return _document(storage)


def test_same_logical_ids_persist_in_canonical_order_and_remain_mutable_after_reload(tmp_path):
    storage = _new_storage(tmp_path)
    document = _register_same_logical_pair(storage, (_CANONICAL_HIGH, _CANONICAL_LOW))

    expected_members = [_CANONICAL_LOW, _CANONICAL_HIGH]
    assert document["indexes"]["by_logical_trade_id"]["FALCON:FALCON15:BTCUSDT:LONG"] == expected_members
    assert document["indexes"]["by_bot"]["FALCON"] == expected_members
    assert set(document["open_trades"]) == set(expected_members)

    updated = core.update_trade_v2(
        storage,
        _CANONICAL_HIGH,
        _CANONICAL_HIGH,
        {"canonical_order_note": "updated-exactly"},
        "same-logical-update-high",
        _generation(storage),
    )
    assert updated.ok is True
    after_update = _document(storage)
    assert after_update["open_trades"][_CANONICAL_HIGH]["canonical_order_note"] == "updated-exactly"
    assert "canonical_order_note" not in after_update["open_trades"][_CANONICAL_LOW]

    closed = core.close_trade_v2(
        storage,
        _CANONICAL_LOW,
        _CANONICAL_LOW,
        "same-logical-close-low",
        "same-logical-close-low-request",
        _generation(storage),
        factual_economics={"pnl_pct": 1.25},
    )
    assert closed.ok is True
    after_close = _document(storage)
    assert _CANONICAL_HIGH in after_close["open_trades"]
    assert _CANONICAL_LOW not in after_close["open_trades"]
    assert after_close["closed_trades"][_CANONICAL_LOW]["execution_id"] == _CANONICAL_LOW
    assert after_close["indexes"]["by_logical_trade_id"]["FALCON:FALCON15:BTCUSDT:LONG"] == [
        _CANONICAL_HIGH,
        _CANONICAL_LOW,
    ]


def test_reverse_same_logical_insertion_has_identical_canonical_persisted_indexes(tmp_path):
    first_storage = _new_storage(tmp_path / "first")
    second_storage = _new_storage(tmp_path / "second")
    first = _register_same_logical_pair(first_storage, (_CANONICAL_HIGH, _CANONICAL_LOW))
    second = _register_same_logical_pair(second_storage, (_CANONICAL_LOW, _CANONICAL_HIGH))

    assert first["indexes"] == second["indexes"]
    assert first["indexes"]["by_logical_trade_id"]["FALCON:FALCON15:BTCUSDT:LONG"] == [
        _CANONICAL_LOW,
        _CANONICAL_HIGH,
    ]
    assert set(first["open_trades"]) == set(second["open_trades"]) == {
        _CANONICAL_LOW,
        _CANONICAL_HIGH,
    }


def test_canonical_indexes_keep_open_rows_before_closed_rows_after_reload(tmp_path):
    storage = _new_storage(tmp_path)
    _register_same_logical_pair(storage, (_CANONICAL_HIGH, _CANONICAL_LOW))

    closed = core.close_trade_v2(
        storage,
        _CANONICAL_LOW,
        _CANONICAL_LOW,
        "open-before-closed-close-low",
        "open-before-closed-close-low-request",
        _generation(storage),
        factual_economics={"pnl_pct": -0.5},
    )

    assert closed.ok is True
    document = _document(storage)
    assert _CANONICAL_HIGH in document["open_trades"]
    assert _CANONICAL_LOW in document["closed_trades"]
    assert document["indexes"]["by_logical_trade_id"]["FALCON:FALCON15:BTCUSDT:LONG"] == [
        _CANONICAL_HIGH,
        _CANONICAL_LOW,
    ]
    assert reader.read_registry_v2(storage.snapshot_path).status == reader.REGISTRY_V2_READ_OK


@pytest.mark.parametrize("field", ["client_order_id", "broker_order_id", "exchange_order_id", "fill_id"])
def test_register_rejects_strong_identity_collision(tmp_path, field):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row("exec-1", **{field: "strong-1"}), "k1").ok
    result = core.register_trade_v2(storage, _row("exec-2", **{field: "strong-1"}), "k2", _generation(storage))

    assert result.status == wal.WAL_CONFLICT
    assert "collision" in " ".join(result.errors)
    assert _generation(storage) == 1


def test_register_requires_exact_execution_lifecycle_identity(tmp_path):
    storage = _new_storage(tmp_path)
    result = core.register_trade_v2(storage, _row(lifecycle_id="other"), "k1", 0)

    assert result.status == wal.WAL_CONFLICT
    assert result.errors == ("execution_id_lifecycle_id_mismatch",)


def test_register_retry_is_idempotent_and_divergent_retry_conflicts(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row()
    first = core.register_trade_v2(storage, row, "same-key", 0)
    journal_before = storage.journal_path.read_bytes()
    retry = core.register_trade_v2(storage, row, "same-key", 0)
    divergent = core.register_trade_v2(
        storage,
        _row(symbol="ETHUSDT", logical_trade_id="FALCON:FALCON15:ETHUSDT:LONG"),
        "same-key",
        0,
    )

    assert retry.ok is True
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == journal_before
    assert divergent.status == wal.WAL_CONFLICT


def test_register_generation_conflict_is_side_effect_free(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    before = storage.journal_path.read_bytes()
    result = core.register_trade_v2(storage, _row("exec-2"), "k2", 0)

    assert result.status == wal.WAL_CONFLICT
    assert result.errors == ("generation_mismatch",)
    assert storage.journal_path.read_bytes() == before


def test_update_selects_only_physical_execution_id(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row("exec-1"), "k1").ok
    assert _register(storage, _row("exec-2", signal_id="signal-2", decision_id="decision-2"), "k2").ok
    result = core.update_trade_v2(storage, "exec-2", "exec-2", {"note": "updated"}, "u1", _generation(storage))
    document = _document(storage)

    assert result.ok is True
    assert document["open_trades"]["exec-2"]["note"] == "updated"
    assert "note" not in document["open_trades"]["exec-1"]


def test_update_rejects_missing_identity_immutable_fields_and_regression(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    missing = core.update_trade_v2(storage, "missing", "missing", {"note": "x"}, "u1", _generation(storage))
    mismatch = core.update_trade_v2(storage, "exec-1", "other", {"note": "x"}, "u2", _generation(storage))
    immutable = core.update_trade_v2(storage, "exec-1", "exec-1", {"symbol": "ETHUSDT"}, "u3", _generation(storage))
    regression = core.update_trade_v2(storage, "exec-1", "exec-1", {"lifecycle_state": schema.ENTRY_INTENT}, "u4", _generation(storage))

    assert missing.status == wal.WAL_NOT_FOUND
    assert mismatch.status == wal.WAL_CONFLICT
    assert immutable.status == core.CORE_PATCH_INVALID
    assert immutable.errors == ("immutable_field:symbol",)
    assert regression.status == core.CORE_STATE_CONFLICT


def test_update_retry_and_divergent_retry_semantics(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "one"}, "u1", 1)
    retry = core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "one"}, "u1", 1)
    divergent = core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "two"}, "u1", 1)

    assert first.ok and retry.event_id == first.event_id
    assert divergent.status == wal.WAL_CONFLICT


def test_update_cannot_replace_a_strong_id_with_another_execution_id(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row("exec-1", client_order_id="client-1"), "k1").ok
    assert _register(storage, _row("exec-2", client_order_id="client-2"), "k2").ok
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"client_order_id": "client-2"},
        "u1",
        2,
    )

    assert result.status == core.CORE_PATCH_INVALID
    assert result.errors == ("strong_id_replacement:client_order_id",)


def _expected_identity(**overrides):
    identity = {
        "execution_id": "exec-1",
        "lifecycle_id": "exec-1",
        "client_order_id": "client-1",
        "broker_order_id": "broker-1",
        "exchange_order_id": "exchange-1",
        "fill_id": "fill-1",
    }
    identity.update(overrides)
    return identity


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("execution_id", "other-execution"),
        ("lifecycle_id", "other-lifecycle"),
        ("client_order_id", "other-client"),
        ("broker_order_id", "other-broker"),
        ("exchange_order_id", "other-exchange"),
        ("fill_id", "other-fill"),
    ],
)
def test_update_expected_identity_mismatch_is_fail_closed(tmp_path, field, value):
    storage = _new_storage(tmp_path)
    row = _row(
        client_order_id="client-1",
        broker_order_id="broker-1",
        exchange_order_id="exchange-1",
        fill_id="fill-1",
    )
    assert _register(storage, row).ok
    before_events = storage.journal_path.read_bytes()
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"note": "must-not-apply"},
        "expected-update",
        1,
        expected_identity=_expected_identity(**{field: value}),
    )

    assert result.status == core.CORE_EXPECTED_IDENTITY_MISMATCH
    assert storage.journal_path.read_bytes() == before_events
    assert _generation(storage) == 1
    assert "note" not in _document(storage)["open_trades"]["exec-1"]


def test_update_expected_identity_correct_succeeds_and_selector_stays_physical(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row(
        client_order_id="client-1",
        broker_order_id="broker-1",
        exchange_order_id="exchange-1",
        fill_id="fill-1",
    )
    assert _register(storage, row).ok
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"note": "expected-ok"},
        "expected-update",
        1,
        expected_identity=_expected_identity(),
    )

    assert result.ok is True
    assert _document(storage)["open_trades"]["exec-1"]["note"] == "expected-ok"


def test_expected_identity_missing_row_strong_id_is_mismatch(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"note": "must-not-apply"},
        "expected-missing",
        1,
        expected_identity={"client_order_id": "client-1"},
    )

    assert result.status == core.CORE_EXPECTED_IDENTITY_MISMATCH
    assert _generation(storage) == 1


def test_partial_close_expected_identity_mismatch_does_not_decrement(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row(client_order_id="client-1")).ok
    before_events = storage.journal_path.read_bytes()
    result = core.partial_close_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        "close-expected",
        3,
        "partial-expected",
        1,
        expected_identity={"client_order_id": "wrong-client"},
    )

    assert result.status == core.CORE_EXPECTED_IDENTITY_MISMATCH
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["remaining_qty"] == 10


def test_full_close_expected_identity_mismatch_does_not_close(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row(client_order_id="client-1")).ok
    before_events = storage.journal_path.read_bytes()
    result = core.close_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        "close-expected",
        "full-expected",
        1,
        expected_identity={"fill_id": "wrong-fill"},
    )

    assert result.status == core.CORE_EXPECTED_IDENTITY_MISMATCH
    assert storage.journal_path.read_bytes() == before_events
    assert "exec-1" in _document(storage)["open_trades"]


def test_reconciliation_expected_identity_mismatch_does_not_apply_economics(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row(client_order_id="client-1")).ok
    before_events = storage.journal_path.read_bytes()
    result = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"fee": 5},
        "reconcile-expected",
        1,
        expected_identity={"broker_order_id": "wrong-broker"},
    )

    assert result.status == core.CORE_EXPECTED_IDENTITY_MISMATCH
    assert storage.journal_path.read_bytes() == before_events
    assert "factual_economics" not in _document(storage)["open_trades"]["exec-1"]


def test_update_can_append_strong_ids_and_rebuilds_unique_indexes(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {
            "client_order_id": "client-1",
            "broker_order_id": "broker-1",
            "exchange_order_id": "exchange-1",
            "fill_id": "fill-1",
        },
        "append-ids",
        1,
    )
    document = _document(storage)

    assert result.ok is True
    for field, value in {
        "client_order_id": "client-1",
        "broker_order_id": "broker-1",
        "exchange_order_id": "exchange-1",
        "fill_id": "fill-1",
    }.items():
        assert document["open_trades"]["exec-1"][field] == value
        assert document["indexes"][f"by_{field}"][value] == "exec-1"


def test_update_can_represent_the_same_strong_id_again(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row(client_order_id="client-1")).ok
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"client_order_id": "client-1"},
        "same-id",
        1,
    )

    assert result.ok is True
    assert _document(storage)["open_trades"]["exec-1"]["client_order_id"] == "client-1"


def test_update_appending_strong_id_owned_by_other_execution_conflicts_before_commit(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row("exec-1"), "k1").ok
    assert _register(storage, _row("exec-2", client_order_id="client-2"), "k2").ok
    before_events = storage.journal_path.read_bytes()
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"client_order_id": "client-2"},
        "collision-update",
        2,
    )

    assert result.status == wal.WAL_CONFLICT
    assert storage.journal_path.read_bytes() == before_events
    assert "client_order_id" not in _document(storage)["open_trades"]["exec-1"]


@pytest.mark.parametrize(
    "field",
    [
        "remaining_qty",
        "closed_qty",
        "close_events",
        "last_close_event_id",
        "exit_qty",
        "close_event_id",
        "close_reason",
        "close_evidence",
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
    ],
)
def test_generic_update_cannot_mutate_close_or_quantity_facts(tmp_path, field):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    before_events = storage.journal_path.read_bytes()
    result = core.update_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {field: 1},
        f"guard-{field}",
        1,
    )

    assert result.status == core.CORE_PATCH_INVALID
    assert any(field in error for error in result.errors)
    assert storage.journal_path.read_bytes() == before_events


def test_generic_update_cannot_produce_partial_or_full_close_state(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    partial_state = core.update_trade_v2(
        storage, "exec-1", "exec-1", {"lifecycle_state": schema.PARTIALLY_CLOSED}, "state-partial", 1
    )
    full_state = core.update_trade_v2(
        storage, "exec-1", "exec-1", {"lifecycle_state": schema.CLOSED_PROVISIONAL}, "state-full", 1
    )

    assert partial_state.status == core.CORE_STATE_CONFLICT
    assert full_state.status == core.CORE_STATE_CONFLICT
    assert _generation(storage) == 1


def test_partial_close_decreases_remainder_preserves_economics_and_stays_open(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    result = core.partial_close_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        "close-1",
        3,
        "pc1",
        1,
        factual_economics={"fee": 0.25, "realized_pnl": 4.0},
    )
    row = _document(storage)["open_trades"]["exec-1"]

    assert result.ok is True
    assert row["remaining_qty"] == 7
    assert row["closed_qty"] == 3
    assert row["lifecycle_state"] == schema.PARTIALLY_CLOSED
    assert row["factual_economics"]["fee"] == 0.25
    assert row["close_events"][0]["close_event_id"] == "close-1"


def test_partial_close_requires_positive_consistent_remainder(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    overclose = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 10, "pc1", 1)
    inconsistent = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-2", 3, "pc2", 1, remaining_qty=6)

    assert overclose.status == wal.WAL_CONFLICT
    assert inconsistent.status == wal.WAL_CONFLICT


def test_partial_close_same_event_is_idempotent_and_divergent_event_conflicts(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc1", 1)
    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc2", 1)
    divergent = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 2, "pc3", 1)

    assert first.ok and retry.ok
    assert retry.event_id == first.event_id
    assert divergent.status == wal.WAL_CONFLICT
    assert _document(storage)["open_trades"]["exec-1"]["remaining_qty"] == 7


def test_full_close_moves_trade_to_closed_with_zero_remainder(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    result = core.close_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        "close-final",
        "fc1",
        1,
        factual_economics={"funding_fee": -0.1},
        broker_evidence={"remaining_qty": 0, "fill_id": "fill-final"},
    )
    document = _document(storage)

    assert result.ok is True
    assert "exec-1" not in document["open_trades"]
    assert document["closed_trades"]["exec-1"]["remaining_qty"] == 0
    assert document["closed_trades"]["exec-1"]["lifecycle_state"] == schema.CLOSED_PROVISIONAL
    assert document["closed_trades"]["exec-1"]["factual_economics"]["funding_fee"] == -0.1


def test_full_close_requires_zero_factual_or_evidence_remainder(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    no_evidence = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc1", 1, remaining_qty=1)
    nonzero_evidence = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "fc2", 1,
        remaining_qty=1, broker_evidence={"remaining_qty": 1},
    )
    accepted_equivalent = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "fc3", 1,
        remaining_qty=1, broker_evidence={"remaining_qty": 0},
    )

    assert no_evidence.status == wal.WAL_INVALID
    assert nonzero_evidence.status == wal.WAL_INVALID
    assert accepted_equivalent.ok is True


def test_full_close_is_exclusive_and_retries_are_idempotent(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc1", 1)
    retry = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc2", 1)
    divergent = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc3", 1, broker_evidence={"fill_id": "different"})
    second_close = core.close_trade_v2(storage, "exec-1", "exec-1", "close-other", "fc4", 1)

    assert first.ok and retry.ok
    assert retry.event_id == first.event_id
    assert divergent.status == wal.WAL_CONFLICT
    assert second_close.status == wal.WAL_CONFLICT


def test_full_close_without_factual_economics_stays_pending_in_open_trades(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok

    result = core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc1", 1)
    document = _document(storage)
    row = document["open_trades"]["exec-1"]
    close_events = row["close_events"]

    assert result.ok
    assert row["lifecycle_state"] == schema.CLOSE_PENDING_RECONCILIATION
    assert row["remaining_qty"] == 0
    assert len(close_events) == 1
    assert close_events[0]["close_event_id"] == "close-pending"
    assert close_events[0]["factual_economics"] == {}
    assert "exec-1" not in document["closed_trades"]


def test_full_close_with_partial_factual_economics_is_provisional_closed(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok

    result = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-provisional", "fc1", 1,
        factual_economics={"fee": 0.2},
    )
    document = _document(storage)
    row = document["closed_trades"]["exec-1"]

    assert result.ok
    assert row["lifecycle_state"] == schema.CLOSED_PROVISIONAL
    assert row["factual_economics"]["fee"] == 0.2
    assert "exec-1" not in document["open_trades"]


def test_full_close_with_explicit_reconciled_status_is_closed_reconciled(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok

    result = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-reconciled", "fc1", 1,
        broker_evidence={"remaining_qty": 0, "reconciliation_status": core.RECONCILIATION_RECONCILED},
    )
    row = _document(storage)["closed_trades"]["exec-1"]

    assert result.ok
    assert row["lifecycle_state"] == schema.CLOSED_RECONCILED
    assert row["reconciliation_status"] == core.RECONCILIATION_RECONCILED
    assert "reconciliation_status" not in row.get("economics", {})
    assert "reconciliation_status" not in row.get("factual_economics", {})


def test_reconciliation_promotes_pending_to_provisional_and_moves_to_closed(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc1", 1).ok

    result = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec1", 2)
    document = _document(storage)
    row = document["closed_trades"]["exec-1"]

    assert result.ok
    assert row["lifecycle_state"] == schema.CLOSED_PROVISIONAL
    assert row["remaining_qty"] == 0
    assert row["factual_economics"]["fee"] == 0.3
    assert "exec-1" not in document["open_trades"]


def test_reconciliation_promotes_pending_to_reconciled_with_explicit_status(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc1", 1).ok

    result = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"fee": 0.3, "reconciliation_status": core.RECONCILIATION_RECONCILED},
        "rec1",
        2,
    )
    row = _document(storage)["closed_trades"]["exec-1"]

    assert result.ok
    assert row["lifecycle_state"] == schema.CLOSED_RECONCILED
    assert row["reconciliation_status"] == core.RECONCILIATION_RECONCILED
    assert row["factual_economics"]["fee"] == 0.3
    assert "reconciliation_status" not in row["factual_economics"]


def test_provisional_reconciliation_promotes_only_with_explicit_status(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-provisional", "fc1", 1,
        factual_economics={"fee": 0.2},
    ).ok
    late_fee = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.4}, "rec1", 2)
    provisional = _document(storage)["closed_trades"]["exec-1"]
    reconciled = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"reconciliation_status": core.RECONCILIATION_RECONCILED},
        "rec2",
        3,
    )
    final = _document(storage)["closed_trades"]["exec-1"]

    assert late_fee.ok
    assert provisional["lifecycle_state"] == schema.CLOSED_PROVISIONAL
    assert reconciled.ok
    assert final["lifecycle_state"] == schema.CLOSED_RECONCILED
    assert final["reconciliation_status"] == core.RECONCILIATION_RECONCILED


def test_reconciled_close_accepts_late_economics_without_reopening(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-reconciled", "fc1", 1,
        factual_economics={"fee": 0.2},
        broker_evidence={"reconciliation_status": core.RECONCILIATION_RECONCILED},
    ).ok

    result = core.reconcile_trade_v2(
        storage, "exec-1", "exec-1", {"funding": -0.1}, "rec1", 2,
    )
    row = _document(storage)["closed_trades"]["exec-1"]

    assert result.ok
    assert row["lifecycle_state"] == schema.CLOSED_RECONCILED
    assert row["reconciliation_status"] == core.RECONCILIATION_RECONCILED
    assert row["factual_economics"]["funding"] == -0.1
    assert "exec-1" not in _document(storage)["open_trades"]


def test_open_and_partial_reconciliation_do_not_close_execution(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    open_result = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.1}, "rec-open", 1)
    open_row = _document(storage)["open_trades"]["exec-1"]
    partial = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-partial", 3, "pc1", 2)
    partial_result = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.2}, "rec-partial", 3)
    partial_row = _document(storage)["open_trades"]["exec-1"]

    assert open_result.ok
    assert open_row["lifecycle_state"] == schema.OPEN
    assert partial.ok and partial_result.ok
    assert partial_row["lifecycle_state"] == schema.PARTIALLY_CLOSED
    assert "exec-1" not in _document(storage)["closed_trades"]


def test_unknown_reconciliation_status_is_invalid_without_journal_mutation(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    before_events = storage.journal_path.read_bytes()

    result = core.reconcile_trade_v2(
        storage, "exec-1", "exec-1", {"fee": 0.1, "reconciliation_status": "UNKNOWN"}, "rec-invalid", 1,
    )

    assert result.status == wal.WAL_INVALID
    assert "reconciliation_status_invalid" in result.errors
    assert storage.journal_path.read_bytes() == before_events


def test_reconciliation_status_survives_idempotent_retry_outside_economics(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc1", 1).ok
    first = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"fee": 0.1, "reconciliation_status": core.RECONCILIATION_RECONCILED},
        "rec1",
        2,
    )
    before_events = storage.journal_path.read_bytes()
    retry = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"fee": 0.1, "reconciliation_status": core.RECONCILIATION_RECONCILED},
        "rec1",
        2,
    )
    row = _document(storage)["closed_trades"]["exec-1"]

    assert first.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert row["reconciliation_status"] == core.RECONCILIATION_RECONCILED
    assert row["factual_economics"]["fee"] == 0.1
    assert "reconciliation_status" not in row["factual_economics"]


def test_exact_partial_retry_runs_semantic_validation_and_returns_original(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-exact", 3, "pc-exact", 1)
    before_events = storage.journal_path.read_bytes()

    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-exact", 3, "pc-exact", 1)

    assert first.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events


def test_exact_partial_retry_fails_closed_after_close_fact_adulteration(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-exact", 3, "pc-exact", 1)
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["open_trades"]["exec-1"].update({"remaining_qty": 10}))

    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-exact", 3, "pc-exact", 1)

    assert first.ok
    assert retry.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_exact_full_close_retry_runs_semantic_validation_and_returns_original(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-exact", "fc-exact", 1,
        factual_economics={"fee": 0.2},
    )
    before_events = storage.journal_path.read_bytes()

    retry = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-exact", "fc-exact", 1,
        factual_economics={"fee": 0.2},
    )

    assert first.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events


def test_exact_full_close_retry_fails_closed_after_remaining_adulteration(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-exact", "fc-exact", 1,
        factual_economics={"fee": 0.2},
    )
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["closed_trades"]["exec-1"].update({"remaining_qty": 1}))

    retry = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-exact", "fc-exact", 1,
        factual_economics={"fee": 0.2},
    )

    assert first.ok
    assert retry.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_exact_open_reconciliation_retry_runs_economics_validation(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.1}, "rec-exact", 1)
    before_events = storage.journal_path.read_bytes()

    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.1}, "rec-exact", 1)

    assert first.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events


def test_exact_open_reconciliation_retry_fails_closed_after_economics_adulteration(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.1}, "rec-exact", 1)
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["open_trades"]["exec-1"]["factual_economics"].update({"fee": 9.0}))

    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.1}, "rec-exact", 1)

    assert first.ok
    assert retry.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_exact_post_close_reconciliation_retry_fails_closed_after_state_adulteration(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "fc1", 1,
        factual_economics={"fee": 0.2},
    ).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec-exact", 2)
    before_events = storage.journal_path.read_bytes()

    def adulterate(document):
        document["closed_trades"]["exec-1"]["lifecycle_state"] = schema.CLOSED_RECONCILED
        document["indexes"] = core._rebuild_candidate(document)["indexes"]

    _rewrite_document(storage, adulterate)
    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec-exact", 2)

    assert first.ok
    assert retry.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


@pytest.mark.parametrize("status", [core.RECONCILIATION_PENDING, core.RECONCILIATION_RECONCILED])
@pytest.mark.parametrize("partial", [False, True])
def test_preclose_reconciliation_status_is_blocked_without_full_close(tmp_path, status, partial):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    expected_generation = 1
    if partial:
        assert core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-partial", 3, "pc1", 1).ok
        expected_generation = 2
    before_events = storage.journal_path.read_bytes()

    result = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"fee": 0.1, "reconciliation_status": status},
        "rec-status",
        expected_generation,
    )
    row = _document(storage)["open_trades"]["exec-1"]

    assert result.status == core.CORE_STATE_CONFLICT
    assert result.errors == ("reconciliation_status_requires_full_close",)
    assert storage.journal_path.read_bytes() == before_events
    assert "reconciliation_status" not in row


def test_all_v25_mutations_keep_operation_ledger_as_derived_empty_cache(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert _document(storage)["operation_ledger"] == {}
    assert core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "u"}, "u1", 1).ok
    assert _document(storage)["operation_ledger"] == {}
    assert core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-partial", 3, "pc1", 2).ok
    assert _document(storage)["operation_ledger"] == {}
    assert core.close_trade_v2(storage, "exec-1", "exec-1", "close-full", "fc1", 3).ok
    assert _document(storage)["operation_ledger"] == {}
    assert core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.5}, "rec1", 4).ok
    assert _document(storage)["operation_ledger"] == {}


def test_close_after_replace_has_no_uncommitted_operation_ledger_record(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    with pytest.raises(CrashInjected):
        core.close_trade_v2(
            storage,
            "exec-1",
            "exec-1",
            "close-crash",
            "fc-crash",
            1,
            fault_hook=_raise_at(wal.AFTER_REPLACE),
        )

    assert _raw_document(storage)["operation_ledger"] == {}
    recovered = wal.recover_temp_wal(storage, lambda _payload: None)
    assert recovered.ok is True
    assert _document(storage)["operation_ledger"] == {}


@pytest.mark.parametrize("operation", ["register", "update", "partial", "full", "reconcile"])
def test_committed_retry_requires_usable_snapshot_before_idempotent_success(tmp_path, operation):
    storage = _new_storage(tmp_path)
    row = _row()
    if operation == "register":
        assert core.register_trade_v2(storage, row, "register-key", 0).ok
        retry = lambda: core.register_trade_v2(storage, row, "register-key", 0)
    else:
        assert _register(storage, row).ok
        if operation == "update":
            assert core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "x"}, "update-key", 1).ok
            retry = lambda: core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "x"}, "update-key", 1)
        elif operation == "partial":
            assert core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "partial-key", 1).ok
            retry = lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "partial-key", 1)
        elif operation == "full":
            assert core.close_trade_v2(storage, "exec-1", "exec-1", "close-1", "full-key", 1).ok
            retry = lambda: core.close_trade_v2(storage, "exec-1", "exec-1", "close-1", "full-key", 1)
        else:
            assert core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1}, "reconcile-key", 1).ok
            retry = lambda: core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1}, "reconcile-key", 1)
    before_events = storage.journal_path.read_bytes()
    storage.snapshot_path.unlink()

    result = retry()

    assert result.ok is False
    assert result.status != wal.WAL_OK
    assert storage.journal_path.read_bytes() == before_events


def test_corrupt_snapshot_digest_blocks_identical_committed_retry(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "x"}, "update-key", 1)
    before_events = storage.journal_path.read_bytes()
    document = _raw_document(storage)
    document["integrity"]["snapshot_digest"] = "corrupt-digest"
    storage.snapshot_path.write_text(wal.canonical_json(document) + "\n", encoding="utf-8")

    result = core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "x"}, "update-key", 1)

    assert committed.ok and result.ok is False
    assert result.status == wal.WAL_SNAPSHOT_INVALID
    assert storage.journal_path.read_bytes() == before_events


def test_partial_close_replay_fails_closed_when_remaining_is_restored(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "partial-key", 1).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["open_trades"]["exec-1"].update({"remaining_qty": 10}))

    result = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "retry-key", 2)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_partial_close_replay_fails_closed_when_row_fact_is_removed(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "partial-key", 1).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["open_trades"]["exec-1"].update({"close_events": []}))

    result = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "retry-key", 2)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_full_close_replay_fails_closed_when_row_is_reopened(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-1", "full-key", 1,
        factual_economics={"fee": 1.0},
    )
    before_events = storage.journal_path.read_bytes()

    def reopen(document):
        row = document["closed_trades"].pop("exec-1")
        row["lifecycle_state"] = schema.OPEN
        document["open_trades"]["exec-1"] = row
        document["indexes"] = core._rebuild_candidate(document)["indexes"]
    _rewrite_document(storage, reopen)
    result = core.close_trade_v2(storage, "exec-1", "exec-1", "close-1", "retry-key", 2)

    assert committed.ok
    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_full_close_replay_fails_closed_when_remaining_is_nonzero(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-1", "full-key", 1,
        factual_economics={"fee": 1.0},
    ).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["closed_trades"]["exec-1"].update({"remaining_qty": 1}))

    result = core.close_trade_v2(storage, "exec-1", "exec-1", "close-1", "retry-key", 2)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_reconciliation_replay_fails_closed_when_factual_economics_is_removed(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.5}, "reconcile-key", 1).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["open_trades"]["exec-1"].update({"factual_economics": {}, "economics": {}}))

    result = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.5}, "retry-key", 2)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_historical_partial_retry_survives_later_partial_close(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-a", 3, "a", 1)
    second = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-b", 2, "b", 2)
    before_events = storage.journal_path.read_bytes()

    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-a", 3, "a-retry", 3)

    assert first.ok and second.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["remaining_qty"] == 5


def test_historical_explicit_partial_retry_uses_each_event_remaining_witness(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a", 1, remaining_qty=7,
    )
    second = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-b", 2, "b", 2, remaining_qty=5,
    )
    before_events = storage.journal_path.read_bytes()

    retry = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a-retry", 3, remaining_qty=7,
    )

    assert first.ok and second.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["remaining_qty"] == 5


def test_historical_explicit_partial_retry_fails_on_wrong_remaining_witness(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a", 1, remaining_qty=7,
    ).ok
    assert core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-b", 2, "b", 2, remaining_qty=5,
    ).ok
    before_events = storage.journal_path.read_bytes()

    def corrupt_witness(document):
        document["open_trades"]["exec-1"]["close_events"][1]["remaining_qty"] = 4

    _rewrite_document(storage, corrupt_witness)
    result = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a-retry", 3, remaining_qty=7,
    )

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_historical_partial_retry_survives_later_full_close(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-a", 3, "a", 1)
    final = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "final", 2)
    before_events = storage.journal_path.read_bytes()

    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-a", 3, "a-retry", 3)

    assert first.ok and final.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    row = _document(storage)["open_trades"]["exec-1"]
    assert row["lifecycle_state"] == schema.CLOSE_PENDING_RECONCILIATION
    assert row["remaining_qty"] == 0


def test_historical_explicit_partial_retry_survives_later_full_close(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a", 1, remaining_qty=7,
    )
    final = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "final", 2,
        factual_economics={"fee": 2.0},
    )
    before_events = storage.journal_path.read_bytes()

    retry = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a-retry", 3, remaining_qty=7,
    )

    assert first.ok and final.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["closed_trades"]["exec-1"]["remaining_qty"] == 0


def test_historical_pending_full_close_retry_after_provisional_reconciliation(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc1", 1)
    promoted = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.2}, "rec1", 2)
    before_events = storage.journal_path.read_bytes()

    retry = core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc-retry", 3)
    row = _document(storage)["closed_trades"]["exec-1"]

    assert first.ok and promoted.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert row["lifecycle_state"] == schema.CLOSED_PROVISIONAL


def test_historical_pending_full_close_retry_after_reconciled_promotion(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc1", 1)
    promoted = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"fee": 0.2, "reconciliation_status": core.RECONCILIATION_RECONCILED},
        "rec1",
        2,
    )
    before_events = storage.journal_path.read_bytes()

    retry = core.close_trade_v2(storage, "exec-1", "exec-1", "close-pending", "fc-retry", 3)
    row = _document(storage)["closed_trades"]["exec-1"]

    assert first.ok and promoted.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert row["lifecycle_state"] == schema.CLOSED_RECONCILED


def test_historical_reconciliation_retry_after_provisional_to_reconciled_promotion(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-provisional", "fc1", 1,
        factual_economics={"fee": 0.2},
    ).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec1", 2)
    promoted = core.reconcile_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        {"reconciliation_status": core.RECONCILIATION_RECONCILED},
        "rec2",
        3,
    )
    before_events = storage.journal_path.read_bytes()

    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec-retry", 4)
    row = _document(storage)["closed_trades"]["exec-1"]

    assert first.ok and promoted.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert row["lifecycle_state"] == schema.CLOSED_RECONCILED


def test_reconciled_state_downgrade_is_historical_divergence(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.close_trade_v2(
        storage,
        "exec-1",
        "exec-1",
        "close-reconciled",
        "fc1",
        1,
        factual_economics={"fee": 0.2},
        broker_evidence={"reconciliation_status": core.RECONCILIATION_RECONCILED},
    ).ok
    assert core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec1", 2).ok
    before_events = storage.journal_path.read_bytes()

    def downgrade(document):
        document["closed_trades"]["exec-1"]["lifecycle_state"] = schema.CLOSED_PROVISIONAL
        document["indexes"] = core._rebuild_candidate(document)["indexes"]

    _rewrite_document(storage, downgrade)
    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.3}, "rec-retry", 3)

    assert retry.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_full_close_replay_diverges_when_current_remaining_is_nonzero(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "fc1", 1,
        factual_economics={"fee": 0.2},
    )
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["closed_trades"]["exec-1"].update({"remaining_qty": 1}))

    retry = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "fc-retry", 2,
        factual_economics={"fee": 0.2},
    )

    assert committed.ok
    assert retry.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_close_pending_without_full_close_journal_fails_closed_on_reconciliation(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok

    def counterfeit_pending(document):
        row = document["open_trades"]["exec-1"]
        row["remaining_qty"] = 0
        row["lifecycle_state"] = schema.CLOSE_PENDING_RECONCILIATION
        document["indexes"] = core._rebuild_candidate(document)["indexes"]

    _rewrite_document(storage, counterfeit_pending)
    before_events = storage.journal_path.read_bytes()
    result = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 0.1}, "rec1", 1)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_historical_reconciliation_retry_survives_later_reconciliation(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.0}, "recon-a", 1)
    second = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 2.0}, "recon-b", 2)
    before_events = storage.journal_path.read_bytes()

    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.0}, "recon-a-retry", 3)

    assert first.ok and second.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["factual_economics"]["fee"] == 2.0


def test_historical_reconciliation_retry_reconstructs_close_economics_chain(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.0}, "recon-a", 1)
    final = core.close_trade_v2(
        storage, "exec-1", "exec-1", "close-final", "final", 2,
        factual_economics={"fee": 2.0},
    )
    before_events = storage.journal_path.read_bytes()

    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.0}, "recon-a-retry", 3)

    assert first.ok and final.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["closed_trades"]["exec-1"]["factual_economics"]["fee"] == 2.0


def test_historical_partial_retry_reconstructs_later_reconciliation_economics(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a", 1,
        factual_economics={"fee": 1.0},
    )
    second = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 2.0}, "recon-b", 2)
    before_events = storage.journal_path.read_bytes()

    retry = core.partial_close_trade_v2(
        storage, "exec-1", "exec-1", "close-a", 3, "a-retry", 3,
        factual_economics={"fee": 1.0},
    )

    assert first.ok and second.ok and retry.ok
    assert retry.event_id == first.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["factual_economics"]["fee"] == 2.0


def test_historical_reconciliation_retry_fails_on_adulterated_economics(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.0}, "recon-a", 1).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["open_trades"]["exec-1"]["factual_economics"].update({"fee": 9.0}))

    result = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.0}, "recon-a-retry", 2)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert storage.journal_path.read_bytes() == before_events


def test_duplicate_identical_prepared_lines_are_one_logical_pending_event(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row()
    with pytest.raises(CrashInjected):
        core.register_trade_v2(storage, row, "register-key", 0, fault_hook=_raise_at(wal.AFTER_PREPARED))
    prepared = wal.read_journal(storage)[0]
    storage.journal_path.open("a", encoding="utf-8").write(wal.canonical_json(prepared.to_dict()) + "\n")

    retry = core.register_trade_v2(storage, row, "register-key", 0)

    assert retry.status == wal.WAL_RECOVERY_REQUIRED
    assert "multiple_pending_events" not in retry.errors

    def resolver(payload):
        def mutate(snapshot, _payload):
            candidate = copy.deepcopy(dict(snapshot))
            candidate["open_trades"][payload["trade"]["execution_id"]] = copy.deepcopy(payload["trade"])
            return core._rebuild_candidate(candidate)
        return mutate

    recovered = wal.recover_temp_wal(storage, resolver)
    final_retry = core.register_trade_v2(storage, row, "register-key", 0)
    assert recovered.ok and final_retry.ok
    assert final_retry.event_id == recovered.event_id


def test_distinct_pending_logical_events_fail_closed_in_core_coherence(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row()
    with pytest.raises(CrashInjected):
        core.register_trade_v2(storage, row, "first-key", 0, fault_hook=_raise_at(wal.AFTER_PREPARED))
    first = wal.read_journal(storage)[0]
    second_row = _row("exec-2", signal_id="signal-exec-2", decision_id="decision-exec-2")
    second_payload = {"trade": second_row}
    second_request = wal.compute_request_digest("REGISTER", "exec-2", "exec-2", "second-key", 0, second_payload)
    second = wal.WalEvent(
        2,
        "event_00000000000000000002",
        "REGISTER",
        "second-key",
        second_request,
        "exec-2",
        "exec-2",
        0,
        1,
        first.before_digest,
        None,
        wal.EVENT_PREPARED,
        None,
        None,
        None,
        "REGISTRY_EXECUTION_IDENTITY_V2_1",
        second_payload,
        None,
        None,
    )
    storage.journal_path.open("a", encoding="utf-8").write(wal.canonical_json(second.to_dict()) + "\n")

    result = core.register_trade_v2(storage, row, "first-key", 0)

    assert result.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert result.errors == ("multiple_pending_events",)


def _parallel_results(calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result(timeout=5) for future in futures]


def test_concurrent_identical_register_has_one_committed_event(tmp_path):
    storage = _new_storage(tmp_path)
    lock = threading.Lock()
    row = _row()
    results = _parallel_results([
        lambda: core.register_trade_v2(storage, row, "same-key", 0, lock=lock),
        lambda: core.register_trade_v2(storage, row, "same-key", 0, lock=lock),
    ])
    committed = [event for event in _events(storage) if event.state == wal.EVENT_COMMITTED]

    assert all(result.ok for result in results)
    assert results[0].event_id == results[1].event_id
    assert len(committed) == 1
    assert set(_document(storage)["open_trades"]) == {"exec-1"}


def test_concurrent_same_logical_distinct_executions_can_commit_serially(tmp_path):
    storage = _new_storage(tmp_path)
    lock = threading.Lock()
    rows = [_row("exec-1"), _row("exec-2", signal_id="signal-exec-2", decision_id="decision-exec-2")]
    initial = _parallel_results([
        lambda: core.register_trade_v2(storage, rows[0], "key-1", 0, lock=lock),
        lambda: core.register_trade_v2(storage, rows[1], "key-2", 0, lock=lock),
    ])
    for index, result in enumerate(initial):
        if not result.ok:
            initial[index] = core.register_trade_v2(storage, rows[index], f"key-{index + 1}-retry", _generation(storage), lock=lock)

    assert all(result.ok for result in initial)
    assert set(_document(storage)["open_trades"]) == {"exec-1", "exec-2"}
    assert len([event for event in _events(storage) if event.state == wal.EVENT_COMMITTED]) == 2


def test_concurrent_strong_id_collision_has_one_winner_and_unique_index(tmp_path):
    storage = _new_storage(tmp_path)
    lock = threading.Lock()
    rows = [_row("exec-1", client_order_id="same-client"), _row("exec-2", client_order_id="same-client")]
    results = _parallel_results([
        lambda: core.register_trade_v2(storage, rows[0], "key-1", 0, lock=lock),
        lambda: core.register_trade_v2(storage, rows[1], "key-2", 0, lock=lock),
    ])
    document = _document(storage)

    assert sum(result.ok for result in results) == 1
    assert sum(result.status == wal.WAL_CONFLICT for result in results) == 1
    assert len(document["indexes"]["by_client_order_id"]) == 1
    assert list(document["indexes"]["by_client_order_id"].values()) in (["exec-1"], ["exec-2"])


def test_concurrent_generation_cas_updates_have_no_lost_update(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    lock = threading.Lock()
    results = _parallel_results([
        lambda: core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "a"}, "u-a", 1, lock=lock),
        lambda: core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "b"}, "u-b", 1, lock=lock),
    ])

    assert sum(result.ok for result in results) == 1
    assert sum(result.status == wal.WAL_CONFLICT for result in results) == 1
    assert _generation(storage) == 2
    assert len([event for event in _events(storage) if event.state == wal.EVENT_COMMITTED]) == 2


def test_concurrent_same_close_event_same_facts_applies_once_with_same_key(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    lock = threading.Lock()
    results = _parallel_results([
        lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "close-key", 1, lock=lock),
        lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "close-key", 1, lock=lock),
    ])
    row = _document(storage)["open_trades"]["exec-1"]

    assert all(result.ok for result in results)
    assert results[0].event_id == results[1].event_id
    assert row["remaining_qty"] == 7
    assert len(row["close_events"]) == 1
    assert len([event for event in _events(storage) if event.operation == core.PARTIAL_CLOSE and event.state == wal.EVENT_COMMITTED]) == 1


def test_concurrent_same_close_event_same_facts_different_keys_replays_original(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    lock = threading.Lock()
    results = _parallel_results([
        lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "close-a", 1, lock=lock),
        lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "close-b", 1, lock=lock),
    ])
    row = _document(storage)["open_trades"]["exec-1"]

    assert all(result.ok for result in results)
    assert results[0].event_id == results[1].event_id
    assert row["remaining_qty"] == 7
    assert len(row["close_events"]) == 1
    assert len([event for event in _events(storage) if event.operation == core.PARTIAL_CLOSE and event.state == wal.EVENT_COMMITTED]) == 1


def test_concurrent_same_close_event_divergent_facts_conflicts(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    lock = threading.Lock()
    results = _parallel_results([
        lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "close-a", 1, lock=lock),
        lambda: core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 2, "close-b", 1, lock=lock),
    ])
    row = _document(storage)["open_trades"]["exec-1"]

    assert sum(result.ok for result in results) == 1
    assert sum(result.status == wal.WAL_CONFLICT for result in results) == 1
    assert row["remaining_qty"] in (7, 8)
    assert len(row["close_events"]) == 1
    wal.read_journal(storage)


def test_partial_close_retry_uses_committed_journal_when_ledger_cache_is_empty(tmp_path):
    storage = _new_storage(tmp_path)
    first = _register(storage, _row())
    assert first.ok
    committed = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc1", 1)
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["operation_ledger"].clear())

    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc2", 1)
    document = _document(storage)

    assert retry.ok is True
    assert retry.event_id == committed.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert document["open_trades"]["exec-1"]["remaining_qty"] == 7


def test_partial_close_retry_survives_operation_ledger_key_removal(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-removed", 3, "pc1", 1)
    before_events = storage.journal_path.read_bytes()

    def remove_ledger(document):
        document.pop("operation_ledger", None)
    _rewrite_document(storage, remove_ledger)
    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-removed", 3, "pc2", 1)

    assert retry.ok is True
    assert retry.event_id == committed.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert "operation_ledger" not in _raw_document(storage)


def test_full_close_retry_uses_committed_journal_when_ledger_cache_is_empty(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc1", 1)
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["operation_ledger"].clear())

    retry = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc2", 1)
    document = _document(storage)

    assert retry.ok is True
    assert retry.event_id == committed.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert document["open_trades"]["exec-1"]["remaining_qty"] == 0
    assert document["open_trades"]["exec-1"]["lifecycle_state"] == schema.CLOSE_PENDING_RECONCILIATION


def test_close_event_divergence_conflicts_from_journal_even_without_ledger(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc1", 1).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["operation_ledger"].clear())

    divergent = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 2, "pc2", 1)

    assert divergent.status == wal.WAL_CONFLICT
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["remaining_qty"] == 7


def test_reconciliation_retry_uses_committed_journal_when_ledger_cache_is_empty(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.25}, "rec1", 1)
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["operation_ledger"].clear())

    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1.25}, "rec2", 1)
    document = _document(storage)

    assert retry.ok is True
    assert retry.event_id == committed.event_id
    assert storage.journal_path.read_bytes() == before_events
    assert document["open_trades"]["exec-1"]["factual_economics"]["fee"] == 1.25


def test_reconciliation_divergent_same_key_conflicts_from_journal_without_ledger(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    assert core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1}, "rec1", 1).ok
    before_events = storage.journal_path.read_bytes()
    _rewrite_document(storage, lambda document: document["operation_ledger"].clear())

    divergent = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 2}, "rec1", 1)

    assert divergent.status == wal.WAL_CONFLICT
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["factual_economics"]["fee"] == 1


def test_ledger_record_without_committed_close_event_never_returns_success(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    close = {
        "close_event_id": "phantom-close",
        "closed_qty": 3,
        "remaining_qty": None,
        "factual_economics": {},
        "kind": "PARTIAL_CLOSE",
    }
    digest = wal.compute_result_digest(close)
    _rewrite_document(
        storage,
        lambda document: document.update({
            "operation_ledger": {
                "close_events": {
                    "exec-1": {
                        "phantom-close": {
                            "evidence_digest": digest,
                            "idempotency_key": "phantom-key",
                            "request_digest": "phantom-request",
                            "operation": core.PARTIAL_CLOSE,
                        }
                    }
                }
            }
        }),
    )
    before_events = storage.journal_path.read_bytes()

    result = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "phantom-close", 3, "new-key", 1)

    assert result.status == wal.WAL_RECOVERY_REQUIRED
    assert storage.journal_path.read_bytes() == before_events
    assert _document(storage)["open_trades"]["exec-1"]["remaining_qty"] == 10


def test_stale_ledger_cannot_override_committed_close_journal(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    committed = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc1", 1)
    before_events = storage.journal_path.read_bytes()

    def stale(document):
        document["operation_ledger"] = {
            "close_events": {
                "exec-1": {
                    "close-1": {
                        "evidence_digest": "stale-digest",
                        "idempotency_key": "stale-key",
                        "request_digest": "stale-request",
                        "operation": core.PARTIAL_CLOSE,
                    }
                }
            }
        }
    _rewrite_document(storage, stale)
    retry = core.partial_close_trade_v2(storage, "exec-1", "exec-1", "close-1", 3, "pc2", 1)

    assert retry.ok is True
    assert retry.event_id == committed.event_id
    assert storage.journal_path.read_bytes() == before_events


def test_manual_external_trade_cannot_be_registered_or_adopted(tmp_path):
    storage = _new_storage(tmp_path)
    result = _register(storage, _row(owner_type=schema.MANUAL_EXTERNAL))

    assert result.ok is False
    assert result.status == schema.REGISTRY_SCHEMA_EXTERNAL_NOT_EXECUTION
    assert _document(storage)["open_trades"] == {}


def test_reconciliation_adds_late_economics_without_reopening(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    close = core.close_trade_v2(storage, "exec-1", "exec-1", "close-final", "fc1", 1)
    result = core.reconcile_trade_v2(
        storage, "exec-1", "exec-1", {"fee": 0.4, "funding": -0.2}, "rec1", 2,
    )
    row = _document(storage)["closed_trades"]["exec-1"]

    assert close.ok and result.ok
    assert row["lifecycle_state"] == schema.CLOSED_PROVISIONAL
    assert row["factual_economics"]["fee"] == 0.4
    assert row["factual_economics"]["funding"] == -0.2


def test_reconciliation_retry_conflict_and_missing_execution(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1}, "rec1", 1)
    retry = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 1}, "rec2", 1)
    divergent = core.reconcile_trade_v2(storage, "exec-1", "exec-1", {"fee": 2}, "rec1", 1)
    missing = core.reconcile_trade_v2(storage, "missing", "missing", {"fee": 1}, "rec3", _generation(storage))

    assert first.ok and retry.ok and retry.event_id == first.event_id
    assert divergent.status == wal.WAL_CONFLICT
    assert missing.status == wal.WAL_NOT_FOUND


def test_core_replays_after_crash_after_prepared(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row()
    with pytest.raises(CrashInjected):
        core.register_trade_v2(storage, row, "k1", 0, fault_hook=_raise_at(wal.AFTER_PREPARED))
    assert wal.inspect_wal_recovery_state(storage).status == wal.PREPARED_PENDING

    def resolver(payload):
        def mutate(snapshot, _payload):
            candidate = copy.deepcopy(dict(snapshot))
            candidate["open_trades"][payload["trade"]["execution_id"]] = copy.deepcopy(payload["trade"])
            return core._rebuild_candidate(candidate)
        return mutate

    recovered = wal.recover_temp_wal(storage, resolver)
    retry = core.register_trade_v2(storage, row, "k1", 0)

    assert recovered.ok and retry.ok
    assert _document(storage)["generation"] == 1
    assert retry.event_id == recovered.event_id


def test_core_replays_after_crash_after_replace(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row()
    with pytest.raises(CrashInjected):
        core.register_trade_v2(storage, row, "k1", 0, fault_hook=_raise_at(wal.AFTER_REPLACE))
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT
    recovered = wal.recover_temp_wal(storage, lambda _payload: None)
    retry = core.register_trade_v2(storage, row, "k1", 0)

    assert recovered.ok and retry.ok
    assert retry.event_id == recovered.event_id


def test_core_recovery_repairs_safe_truncated_tail_without_reapplying(tmp_path):
    storage = _new_storage(tmp_path)
    row = _row()
    first = core.register_trade_v2(storage, row, "k1", 0)
    prefix = storage.journal_path.read_bytes()
    storage.journal_path.open("ab").write(b"partial-tail")

    recovered = wal.recover_temp_wal(storage, lambda _payload: pytest.fail("must not replay committed event"))
    retry = core.register_trade_v2(storage, row, "k1", 0)

    assert recovered.ok is True
    assert storage.journal_path.read_bytes() == prefix
    assert retry.ok and retry.event_id == first.event_id
    assert _generation(storage) == 1


def test_core_operations_are_isolated_by_injected_storage(tmp_path):
    first = _new_storage(tmp_path / "first")
    second = _new_storage(tmp_path / "second")
    assert _register(first, _row("exec-1"), "k1").ok
    assert _register(second, _row("exec-2"), "k2").ok

    assert set(_document(first)["open_trades"]) == {"exec-1"}
    assert set(_document(second)["open_trades"]) == {"exec-2"}
    assert len(_events(first)) == len(_events(second)) == 2


def test_core_source_has_no_external_or_production_writer_api():
    source = Path(core.__file__).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "subprocess" not in source
    assert "write_text" not in source
    assert "write_bytes" not in source
    assert "os.system" not in source


def test_snapshot_witness_and_generation_advance_with_each_commit(tmp_path):
    storage = _new_storage(tmp_path)
    assert _register(storage, _row()).ok
    first = _document(storage)
    assert first["integrity"]["last_committed_event_seq"] == 0
    assert first["wal"]["materialized_seq"] == 1
    assert first["wal"]["state"] == wal.SNAPSHOT_COMMITTED
    assert core.update_trade_v2(storage, "exec-1", "exec-1", {"note": "ok"}, "u1", 1).ok
    second = _document(storage)
    assert second["generation"] == 2
    assert second["integrity"]["last_committed_event_seq"] == 0
    assert second["wal"]["materialized_seq"] == 2
