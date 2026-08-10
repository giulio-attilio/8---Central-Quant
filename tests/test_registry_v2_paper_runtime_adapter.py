from __future__ import annotations

import ast
from dataclasses import replace
import json
import multiprocessing
from pathlib import Path
import queue
import threading
import time

import pytest

import registry_execution_schema as schema
import registry_v2_paper_runtime_adapter as paper
import registry_v2_reader as reader
import registry_v2_wal as wal


_IDENTITY_ONE = "exec_00000000-0000-4000-8000-000000000001"
_IDENTITY_TWO = "exec_00000000-0000-4000-8000-000000000002"


class _CrashInjected(RuntimeError):
    pass


def _position(**overrides):
    position = {
        "setup": "TURTLE20",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry": 100.0,
        "initial_stop": 95.0,
        "stop": 95.0,
        "tp50": 105.0,
        "signal_ts": 1_700_000_000,
        "opened_candle_ts": 1_700_000_000,
        "status": "OPEN",
        "tp50_hit": False,
        "be_moved": False,
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "management_cycles": 0,
    }
    position.update(overrides)
    return position


def _adapter(tmp_path: Path, *, enabled: bool = True):
    return paper.RegistryV2PaperRuntimeAdapter(enabled=enabled, storage_dir=tmp_path)


def _register(adapter, position, **kwargs):
    return adapter.register_turtle_paper(
        position,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        **kwargs,
    )


def _read_register(adapter, position, **kwargs):
    return adapter.read_turtle_paper_committed_register(
        position,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        **kwargs,
    )


def _update(adapter, position, *, event="TP50", updates=None, **kwargs):
    return adapter.update_turtle_paper(
        position,
        event=event,
        updates={} if updates is None else updates,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        **kwargs,
    )


def _close(adapter, position, **kwargs):
    return adapter.close_turtle_paper(
        position,
        exit_price=106.0,
        reason="TURTLE_EXIT",
        result_pct=6.0,
        result_r=1.2,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        **kwargs,
    )


def _storage_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / paper.REGISTRY_V2_PAPER_SNAPSHOT_FILENAME,
        tmp_path / paper.REGISTRY_V2_PAPER_JOURNAL_FILENAME,
    )


def _document(tmp_path: Path):
    snapshot_path, _journal_path = _storage_paths(tmp_path)
    result = reader.read_registry_v2(snapshot_path)
    assert result.ok, result.errors
    assert result.document is not None
    return result.document


def _events(tmp_path: Path):
    snapshot_path, journal_path = _storage_paths(tmp_path)
    storage = wal.RegistryV2WalStorage(
        snapshot_path=snapshot_path,
        journal_path=journal_path,
        lock_path=tmp_path / paper.REGISTRY_V2_PAPER_LOCK_FILENAME,
        backup_dir=tmp_path / paper.REGISTRY_V2_PAPER_BACKUP_DIRNAME,
    )
    return wal.read_journal(storage)


def _process_register(
    storage_dir: str,
    execution_id: str,
    idempotency_key: str,
    entry: float,
    result_queue,
    *,
    started=None,
    core_entered=None,
    release=None,
    timeout_seconds: float | None = None,
):
    """Spawn-safe local worker for the adapter's interprocess lock tests."""

    if timeout_seconds is not None:
        paper.REGISTRY_V2_PAPER_RUNTIME_LOCK_TIMEOUT_SECONDS = timeout_seconds
    if started is not None:
        started.set()
    position_kwargs = {"entry": entry}
    if execution_id is not None:
        position_kwargs.update(
            {
                "execution_id": execution_id,
                "lifecycle_id": execution_id,
            }
        )
    position = _position(**position_kwargs)
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=storage_dir)

    def hold_core(stage):
        if stage == wal.BEFORE_PREPARED:
            if core_entered is not None:
                core_entered.set()
            if release is not None:
                release.wait(8)

    result = _register(
        adapter,
        position,
        idempotency_key=idempotency_key,
        fault_hook=hold_core if core_entered is not None else None,
    )
    result_queue.put({"result": result.to_dict(), "position": position})


def _process_hold_runtime_lock(storage_dir: str, entered, release):
    """Hold only the synchronization file, without writing Registry data."""

    lock_path = Path(storage_dir) / paper.REGISTRY_V2_PAPER_LOCK_FILENAME
    with paper._RuntimeRegistryLock(lock_path, 5.0):
        entered.set()
        release.wait(8)


def _join_process(process, *, timeout: float = 10.0):
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(5)
        pytest.fail(f"child process did not finish: pid={process.pid}")
    assert process.exitcode == 0


def _queue_result(result_queue):
    try:
        return result_queue.get(timeout=5)
    except queue.Empty as exc:
        pytest.fail("child process did not publish a result")
        raise AssertionError("unreachable") from exc


def _track_runtime_lock(monkeypatch):
    state = {"depth": 0}
    original_enter = paper._RuntimeRegistryLock.__enter__
    original_exit = paper._RuntimeRegistryLock.__exit__

    def tracked_enter(lock):
        result = original_enter(lock)
        state["depth"] += 1
        return result

    def tracked_exit(lock, exc_type, exc, traceback):
        try:
            return original_exit(lock, exc_type, exc, traceback)
        finally:
            state["depth"] -= 1

    monkeypatch.setattr(paper._RuntimeRegistryLock, "__enter__", tracked_enter)
    monkeypatch.setattr(paper._RuntimeRegistryLock, "__exit__", tracked_exit)
    return state


def test_gate_parser_is_strict_false_by_default():
    assert paper.parse_registry_v2_paper_write_enabled(None) is False
    assert paper.parse_registry_v2_paper_write_enabled("") is False
    assert paper.parse_registry_v2_paper_write_enabled("false") is False
    assert paper.parse_registry_v2_paper_write_enabled("1") is False
    assert paper.parse_registry_v2_paper_write_enabled("yes") is False
    assert paper.parse_registry_v2_paper_write_enabled("TRUE") is True
    assert paper.RegistryV2PaperRuntimeAdapter(enabled=False).enabled is False


def test_gate_off_is_a_noop_without_identity_or_v2_files(tmp_path):
    position = _position()
    before = dict(position)

    result = _register(_adapter(tmp_path, enabled=False), position)

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_DISABLED
    assert result.enabled is False
    assert result.write_attempted is False
    assert position == before
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("execution_mode", "registry_mode"),
    (
        (schema.LIVE, schema.PAPER),
        (schema.VERIFY, schema.VERIFY),
        (schema.PAPER, schema.REAL),
        (schema.PAPER, schema.UNKNOWN),
        (schema.PAPER, schema.CONFLICT),
        (None, schema.PAPER),
        ("", schema.PAPER),
    ),
)
def test_non_paper_modes_are_rejected_before_identity_or_storage_mutation(
    tmp_path,
    execution_mode,
    registry_mode,
):
    position = _position()

    result = _adapter(tmp_path).register_turtle_paper(
        position,
        execution_mode=execution_mode,
        registry_mode=registry_mode,
    )

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_MODE_REJECTED
    assert result.eligible is False
    assert result.write_attempted is False
    assert "execution_id" not in position
    assert list(tmp_path.iterdir()) == []


def test_enabled_route_requires_explicit_existing_absolute_storage_before_identity():
    position = _position()

    result = paper.RegistryV2PaperRuntimeAdapter(enabled=True).register_turtle_paper(
        position,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
    )

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_STORAGE_REQUIRED
    assert result.storage_configured is False
    assert result.write_attempted is False
    assert "execution_id" not in position


def test_invalid_storage_is_rejected_before_any_runtime_lock_file_is_created(tmp_path):
    missing_directory = tmp_path / "not-configured"
    position = _position()

    result = paper.RegistryV2PaperRuntimeAdapter(
        enabled=True,
        storage_dir=missing_directory,
    ).register_turtle_paper(
        position,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
    )

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_STORAGE_INVALID
    assert not missing_directory.exists()
    assert not (missing_directory / paper.REGISTRY_V2_PAPER_LOCK_FILENAME).exists()
    assert "execution_id" not in position


def test_register_writes_only_v2_under_explicit_temp_path_and_preserves_v1_bytes(tmp_path):
    v1_path = tmp_path / "trade_registry.json"
    v1_bytes = b'{"v1":"unchanged"}\n'
    v1_path.write_bytes(v1_bytes)
    position = _position()

    result = _register(_adapter(tmp_path), position)
    snapshot_path, journal_path = _storage_paths(tmp_path)

    assert result.ok is True
    assert result.eligible is True
    assert result.write_attempted is True
    assert result.write_committed is True
    assert result.event_state == wal.EVENT_COMMITTED
    assert snapshot_path.exists()
    assert journal_path.exists()
    assert v1_path.read_bytes() == v1_bytes
    assert {path.name for path in tmp_path.iterdir()} == {
        "trade_registry.json",
        paper.REGISTRY_V2_PAPER_SNAPSHOT_FILENAME,
        paper.REGISTRY_V2_PAPER_JOURNAL_FILENAME,
        paper.REGISTRY_V2_PAPER_LOCK_FILENAME,
    }


def test_register_generates_once_with_accepted_identity_helper_and_marks_legacy_missing(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        paper,
        "generate_execution_lifecycle_id",
        lambda: calls.append("generated") or _IDENTITY_ONE,
    )
    position = _position()

    result = _register(_adapter(tmp_path), position)
    row = _document(tmp_path)["open_trades"][_IDENTITY_ONE]

    assert result.ok is True
    assert calls == ["generated"]
    assert position["execution_id"] == position["lifecycle_id"] == _IDENTITY_ONE
    assert row["execution_id"] == row["lifecycle_id"] == _IDENTITY_ONE
    assert row["legacy_missing"] is True
    assert row["legacy_missing_marker"] == schema.LEGACY_MISSING
    assert "signal_id" not in row
    assert "decision_id" not in row
    assert row["quantity"] == row["remaining_qty"] == 1


def test_register_preserves_valid_existing_identity_and_persists_one_stable_key(tmp_path):
    position = _position(execution_id=_IDENTITY_ONE, lifecycle_id=_IDENTITY_ONE)

    result = _register(_adapter(tmp_path), position, idempotency_key="turtle-birth-key")

    assert result.ok is True
    assert position["execution_id"] == _IDENTITY_ONE
    assert position["lifecycle_id"] == _IDENTITY_ONE
    assert position["registry_v2_register_idempotency_key"] == "turtle-birth-key"
    assert position["registry_v2_routed"] is True


def test_identical_register_retry_replays_committed_event_and_restart_preserves_identity(tmp_path):
    position = _position()
    first = _register(_adapter(tmp_path), position)
    first_events = _events(tmp_path)
    reloaded = _adapter(tmp_path)

    second = _register(reloaded, position)

    assert first.ok is True
    assert second.ok is True
    assert second.event_id == first.event_id
    assert second.event_seq == first.event_seq
    assert second.target_generation == first.target_generation
    assert position["execution_id"] == position["lifecycle_id"] == first.execution_id
    assert len(_events(tmp_path)) == len(first_events) == 2


def test_divergent_register_retry_with_same_stable_key_conflicts(tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()
    position["entry"] = 101.0

    result = _register(_adapter(tmp_path), position)

    assert result.ok is False
    assert result.status == wal.WAL_CONFLICT
    assert result.write_committed is False
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_two_same_logical_turtle_executions_remain_independently_mutable_after_reload(tmp_path):
    adapter = _adapter(tmp_path)
    first = _position()
    second = _position()
    first_result = _register(adapter, first)
    second_result = _register(adapter, second)

    assert first_result.ok is second_result.ok is True
    assert first_result.execution_id != second_result.execution_id
    assert _document(tmp_path)["indexes"]["by_logical_trade_id"]["TURTLE:TURTLE20:BTCUSDT:LONG"] == sorted(
        [first_result.execution_id, second_result.execution_id]
    )

    reloaded = _adapter(tmp_path)
    updated = _update(reloaded, first, updates={"exact_marker": "first-only"})
    closed = _close(reloaded, second)
    document = _document(tmp_path)

    assert updated.ok is True
    assert closed.ok is True
    assert document["open_trades"][first_result.execution_id]["exact_marker"] == "first-only"
    assert second_result.execution_id not in document["open_trades"]
    assert document["closed_trades"][second_result.execution_id]["execution_id"] == second_result.execution_id


def test_update_and_close_reuse_exact_identity_without_logical_selector(tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    registered = _register(adapter, position)
    identity = position["execution_id"]

    updated = _update(adapter, position, updates={"price": 105.0})
    closed = _close(adapter, position)
    document = _document(tmp_path)

    assert registered.execution_id == updated.execution_id == closed.execution_id == identity
    assert registered.lifecycle_id == updated.lifecycle_id == closed.lifecycle_id == identity
    assert document["closed_trades"][identity]["close_events"][0]["close_event_id"] == position[
        "registry_v2_close_event_id"
    ]
    assert "logical_trade_id" not in _events(tmp_path)[-1].mutation_payload


def test_wrong_execution_lifecycle_pair_fails_closed_without_mutation(tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()
    position["lifecycle_id"] = _IDENTITY_TWO

    result = _update(adapter, position)

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


@pytest.mark.parametrize("owner_type", (schema.MANUAL_EXTERNAL, "EXTERNAL"))
def test_external_positions_are_not_adopted(tmp_path, owner_type):
    position = _position(owner_type=owner_type)

    result = _register(_adapter(tmp_path), position)

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID
    assert result.write_attempted is False
    assert "execution_id" not in position
    assert list(tmp_path.iterdir()) == []


def test_generation_conflict_fails_explicitly_without_a_guessed_generation(monkeypatch, tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()
    monkeypatch.setattr(adapter, "_generation_for_request", lambda *_args: 0)

    result = _update(adapter, position, updates={"generation_conflict": True})

    assert result.status == wal.WAL_CONFLICT
    assert "generation_mismatch" in result.errors
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_clean_restart_reports_clean_wal_and_allows_next_exact_mutation(tmp_path):
    position = _position()
    assert _register(_adapter(tmp_path), position).ok is True

    result = _update(_adapter(tmp_path), position, updates={"after_restart": True})

    assert result.ok is True
    assert result.wal_status == wal.CLEAN
    assert result.core_status == wal.WAL_OK
    assert result.write_committed is True


def test_prepared_pending_blocks_new_write_without_v1_or_repair(tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True

    def crash_after_prepared(stage):
        if stage == wal.AFTER_PREPARED:
            raise _CrashInjected(stage)

    with pytest.raises(_CrashInjected):
        _update(adapter, position, updates={"pending": True}, fault_hook=crash_after_prepared)
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()

    blocked = _register(_adapter(tmp_path), _position(symbol="ETHUSDT"))

    assert blocked.status == paper.REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
    assert blocked.recovery_required is True
    assert blocked.wal_status == wal.PREPARED_PENDING
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_snapshot_journal_divergence_blocks_new_write(tmp_path):
    position = _position()
    assert _register(_adapter(tmp_path), position).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    document["generation"] = 99
    document["integrity"]["snapshot_digest"] = wal.compute_snapshot_digest(document)
    snapshot_path.write_text(wal.canonical_json(document) + "\n", encoding="utf-8")
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()

    blocked = _register(_adapter(tmp_path), _position(symbol="ETHUSDT"))

    assert blocked.status == paper.REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
    assert blocked.wal_status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert blocked.recovery_required is True
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_journal_corruption_blocks_new_write(tmp_path):
    position = _position()
    assert _register(_adapter(tmp_path), position).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    journal_path.write_text("{not-json}\n", encoding="utf-8")
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()

    blocked = _register(_adapter(tmp_path), _position(symbol="ETHUSDT"))

    assert blocked.status == paper.REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
    assert blocked.wal_status == wal.JOURNAL_CORRUPT
    assert blocked.recovery_required is True
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_disabling_gate_preserves_existing_v2_evidence_and_writes_nothing(tmp_path):
    position = _position()
    assert _register(_adapter(tmp_path), position).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()

    result = _update(_adapter(tmp_path, enabled=False), position)

    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_DISABLED
    assert result.write_attempted is False
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_event_committed_journal_remains_the_retry_authority(tmp_path):
    position = _position()
    first = _register(_adapter(tmp_path), position)
    committed = [event for event in _events(tmp_path) if event.state == wal.EVENT_COMMITTED]

    second = _register(_adapter(tmp_path), position)

    assert len(committed) == 1
    assert committed[0].event_id == first.event_id == second.event_id
    assert committed[0].idempotency_key == position["registry_v2_register_idempotency_key"]
    assert _document(tmp_path)["operation_ledger"] == {}


@pytest.mark.parametrize(
    ("event", "updates"),
    (
        ("TP50", {"price": 105.0, "candles_to_tp50": 3}),
        ("BE", {"new_sl": 100.0}),
    ),
)
def test_one_shot_update_retry_replays_the_same_committed_event_after_adapter_restart(
    tmp_path,
    event,
    updates,
):
    position = _position()
    assert _register(_adapter(tmp_path), position).ok is True

    first = _update(_adapter(tmp_path), position, event=event, updates=updates)
    second = _update(_adapter(tmp_path), position, event=event, updates=updates)

    assert first.ok is second.ok is True
    assert second.event_id == first.event_id
    assert second.event_seq == first.event_seq
    assert second.expected_generation == first.expected_generation
    updates_in_journal = [
        item for item in _events(tmp_path) if item.state == wal.EVENT_COMMITTED and item.operation == "UPDATE"
    ]
    assert len(updates_in_journal) == 1
    assert first.event_id is not None
    assert f"turtle-paper-update:{position['execution_id']}:{event}" in {
        item.idempotency_key for item in _events(tmp_path)
    }


@pytest.mark.parametrize(
    ("event", "first_updates", "divergent_updates"),
    (
        ("TP50", {"price": 105.0}, {"price": 106.0}),
        ("BE", {"new_sl": 100.0}, {"new_sl": 101.0}),
    ),
)
def test_one_shot_update_divergent_retry_conflicts_under_the_same_factual_key(
    tmp_path,
    event,
    first_updates,
    divergent_updates,
):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True
    assert _update(adapter, position, event=event, updates=first_updates).ok is True
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()

    divergent = _update(
        _adapter(tmp_path),
        position,
        event=event,
        updates=divergent_updates,
    )

    assert divergent.ok is False
    assert divergent.status == wal.WAL_CONFLICT
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_runtime_lock_wraps_inspection_generation_all_core_operations_and_result(monkeypatch, tmp_path):
    adapter = _adapter(tmp_path)
    position = _position()
    state = _track_runtime_lock(monkeypatch)
    observed = []

    original_inspect = paper.wal.inspect_wal_recovery_state

    def inspect_while_locked(storage):
        assert state["depth"] == 1
        observed.append("inspect")
        return original_inspect(storage)

    original_generation = adapter._generation_for_request

    def generation_while_locked(*args):
        assert state["depth"] == 1
        observed.append(f"generation:{args[1]}")
        return original_generation(*args)

    original_result = adapter._core_result

    def result_while_locked(*args):
        assert state["depth"] == 1
        observed.append("result")
        return original_result(*args)

    monkeypatch.setattr(paper.wal, "inspect_wal_recovery_state", inspect_while_locked)
    monkeypatch.setattr(adapter, "_generation_for_request", generation_while_locked)
    monkeypatch.setattr(adapter, "_core_result", result_while_locked)

    for name in ("register_trade_v2", "update_trade_v2", "close_trade_v2"):
        original_core_call = getattr(paper.core, name)

        def core_while_locked(*args, _name=name, _original=original_core_call, **kwargs):
            assert state["depth"] == 1
            observed.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(paper.core, name, core_while_locked)

    assert _register(adapter, position).ok is True
    assert _update(adapter, position, updates={"price": 105.0}).ok is True
    assert _close(adapter, position).ok is True

    assert state["depth"] == 0
    assert observed[0] == "inspect"
    assert "generation:REGISTER" in observed
    assert "generation:UPDATE" in observed
    assert "generation:FULL_CLOSE" in observed
    assert {"register_trade_v2", "update_trade_v2", "close_trade_v2"}.issubset(observed)
    assert observed.count("result") == 3


def test_two_adapter_instances_serialize_recovery_inspection_for_one_path(monkeypatch, tmp_path):
    first_adapter = _adapter(tmp_path)
    second_adapter = _adapter(tmp_path)
    first_position = _position(execution_id=_IDENTITY_ONE, lifecycle_id=_IDENTITY_ONE)
    second_position = _position(execution_id=_IDENTITY_TWO, lifecycle_id=_IDENTITY_TWO)
    release = threading.Event()
    first_inspection = threading.Event()
    attempts = threading.Event()
    monitor = threading.Lock()
    active_inspections = 0
    max_active_inspections = 0
    inspection_calls = 0
    original_inspect = paper.wal.inspect_wal_recovery_state

    def blocking_first_inspection(storage):
        nonlocal active_inspections, max_active_inspections, inspection_calls
        with monitor:
            inspection_calls += 1
            current_call = inspection_calls
            active_inspections += 1
            max_active_inspections = max(max_active_inspections, active_inspections)
        try:
            if current_call == 1:
                first_inspection.set()
                assert release.wait(5)
            return original_inspect(storage)
        finally:
            with monitor:
                active_inspections -= 1

    monkeypatch.setattr(paper.wal, "inspect_wal_recovery_state", blocking_first_inspection)
    results = {}
    errors = []

    def invoke(name, adapter, position):
        try:
            results[name] = _register(adapter, position)
        except BaseException as error:
            errors.append(error)

    first_thread = threading.Thread(target=invoke, args=("first", first_adapter, first_position))
    second_thread = threading.Thread(target=invoke, args=("second", second_adapter, second_position))
    try:
        first_thread.start()
        assert first_inspection.wait(5)
        attempts.set()
        second_thread.start()
        assert attempts.is_set()
        second_thread.join(0.15)
        assert second_thread.is_alive()
        with monitor:
            assert inspection_calls == 1
            assert max_active_inspections == 1
    finally:
        release.set()
        first_thread.join(5)
        second_thread.join(5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert results["first"].ok is results["second"].ok is True


def test_two_threads_cannot_enter_core_mutation_concurrently(monkeypatch, tmp_path):
    adapter = _adapter(tmp_path)
    first_position = _position(execution_id=_IDENTITY_ONE, lifecycle_id=_IDENTITY_ONE)
    second_position = _position(execution_id=_IDENTITY_TWO, lifecycle_id=_IDENTITY_TWO)
    release = threading.Event()
    first_core = threading.Event()
    second_core = threading.Event()
    calls = 0
    original_register = paper.core.register_trade_v2

    def blocking_register(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_core.set()
            assert release.wait(5)
        else:
            second_core.set()
        return original_register(*args, **kwargs)

    monkeypatch.setattr(paper.core, "register_trade_v2", blocking_register)
    results = []
    errors = []

    def invoke(position):
        try:
            results.append(_register(adapter, position))
        except BaseException as error:
            errors.append(error)

    first_thread = threading.Thread(target=invoke, args=(first_position,))
    second_thread = threading.Thread(target=invoke, args=(second_position,))
    try:
        first_thread.start()
        assert first_core.wait(5)
        second_thread.start()
        assert not second_core.wait(0.15)
    finally:
        release.set()
        first_thread.join(5)
        second_thread.join(5)

    assert errors == []
    assert len(results) == 2
    assert all(result.ok for result in results)
    assert calls == 2


def test_different_registry_paths_have_independent_process_local_locks(monkeypatch, tmp_path):
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    release = threading.Event()
    both_inspections = threading.Event()
    seen_paths = set()
    monitor = threading.Lock()
    original_inspect = paper.wal.inspect_wal_recovery_state

    def wait_for_both_paths(storage):
        lock_path = str(storage.lock_path.resolve())
        should_wait = False
        with monitor:
            if lock_path not in seen_paths:
                seen_paths.add(lock_path)
                should_wait = True
                if len(seen_paths) == 2:
                    both_inspections.set()
        if should_wait:
            assert release.wait(5)
        return original_inspect(storage)

    monkeypatch.setattr(paper.wal, "inspect_wal_recovery_state", wait_for_both_paths)
    results = []
    first_thread = threading.Thread(
        target=lambda: results.append(_register(_adapter(first_path), _position(execution_id=_IDENTITY_ONE, lifecycle_id=_IDENTITY_ONE)))
    )
    second_thread = threading.Thread(
        target=lambda: results.append(_register(_adapter(second_path), _position(execution_id=_IDENTITY_TWO, lifecycle_id=_IDENTITY_TWO)))
    )
    try:
        first_thread.start()
        second_thread.start()
        assert both_inspections.wait(2)
    finally:
        release.set()
        first_thread.join(5)
        second_thread.join(5)

    assert len(results) == 2
    assert all(result.ok for result in results)


def test_process_local_lock_timeout_fails_closed_without_identity_or_registry_mutation(monkeypatch, tmp_path):
    monkeypatch.setattr(paper, "REGISTRY_V2_PAPER_RUNTIME_LOCK_TIMEOUT_SECONDS", 0.05)
    generated = []
    monkeypatch.setattr(
        paper,
        "generate_execution_lifecycle_id",
        lambda: generated.append("generated") or _IDENTITY_TWO,
    )
    release = threading.Event()
    first_inspection = threading.Event()
    original_inspect = paper.wal.inspect_wal_recovery_state
    calls = 0

    def blocking_first_inspection(storage):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_inspection.set()
            assert release.wait(5)
        return original_inspect(storage)

    monkeypatch.setattr(paper.wal, "inspect_wal_recovery_state", blocking_first_inspection)
    first_position = _position(execution_id=_IDENTITY_ONE, lifecycle_id=_IDENTITY_ONE)
    second_position = _position()
    first_result = []
    first_thread = threading.Thread(target=lambda: first_result.append(_register(_adapter(tmp_path), first_position)))
    try:
        first_thread.start()
        assert first_inspection.wait(5)
        timeout = _register(_adapter(tmp_path), second_position)
        assert timeout.status == paper.REGISTRY_PERSISTENCE_LOCK_TIMEOUT
        assert timeout.ok is False
        assert timeout.eligible is True
        assert timeout.write_attempted is False
        assert timeout.write_committed is False
        assert timeout.recovery_required is False
        assert "execution_id" not in second_position
        assert "lifecycle_id" not in second_position
        assert generated == []
    finally:
        release.set()
        first_thread.join(5)

    assert first_result and first_result[0].ok is True
    assert {event.execution_id for event in _events(tmp_path) if event.state == wal.EVENT_COMMITTED} == {_IDENTITY_ONE}


def test_recovery_blocked_result_is_constructed_while_runtime_lock_is_held(monkeypatch, tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True

    def crash_after_prepared(stage):
        if stage == wal.AFTER_PREPARED:
            raise _CrashInjected(stage)

    with pytest.raises(_CrashInjected):
        _update(adapter, position, updates={"pending": True}, fault_hook=crash_after_prepared)

    state = _track_runtime_lock(monkeypatch)
    original_inspect = adapter._inspect_after_runtime_lock

    def inspected_while_locked(preflight):
        assert state["depth"] == 1
        result = original_inspect(preflight)
        assert state["depth"] == 1
        assert isinstance(result, paper.RegistryV2PaperRuntimeResult)
        assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
        return result

    monkeypatch.setattr(adapter, "_inspect_after_runtime_lock", inspected_while_locked)
    blocked = _register(adapter, _position(symbol="ETHUSDT"))

    assert blocked.status == paper.REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
    assert state["depth"] == 0


def test_interprocess_runtime_lock_serializes_core_mutation(tmp_path):
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    release = context.Event()
    first_started = context.Event()
    first_core = context.Event()
    second_started = context.Event()
    second_core = context.Event()
    first = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_ONE, "process-first", 100.0, results),
        kwargs={"started": first_started, "core_entered": first_core, "release": release},
    )
    second = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_TWO, "process-second", 100.0, results),
        kwargs={"started": second_started, "core_entered": second_core},
    )
    try:
        first.start()
        assert first_started.wait(5)
        assert first_core.wait(5)
        second.start()
        assert second_started.wait(5)
        assert not second_core.wait(0.25)
    finally:
        release.set()
        _join_process(first)
        _join_process(second)

    child_results = [_queue_result(results), _queue_result(results)]
    assert all(item["result"]["ok"] is True for item in child_results)
    committed = [event for event in _events(tmp_path) if event.state == wal.EVENT_COMMITTED]
    assert [event.execution_id for event in committed] == [_IDENTITY_ONE, _IDENTITY_TWO]


def test_interprocess_same_request_is_idempotent_and_divergence_conflicts(tmp_path):
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    release = context.Event()
    first_core = context.Event()
    first = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_ONE, "same-request", 100.0, results),
        kwargs={"core_entered": first_core, "release": release},
    )
    same_retry = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_ONE, "same-request", 100.0, results),
    )
    try:
        first.start()
        assert first_core.wait(5)
        same_retry.start()
    finally:
        release.set()
        _join_process(first)
        _join_process(same_retry)

    first_result, retry_result = _queue_result(results), _queue_result(results)
    assert first_result["result"]["ok"] is retry_result["result"]["ok"] is True
    assert first_result["result"]["event_id"] == retry_result["result"]["event_id"]
    assert len([event for event in _events(tmp_path) if event.state == wal.EVENT_COMMITTED]) == 1

    divergent_results = context.Queue()
    divergent = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_ONE, "same-request", 101.0, divergent_results),
    )
    divergent.start()
    _join_process(divergent)
    divergent_result = _queue_result(divergent_results)["result"]

    assert divergent_result["ok"] is False
    assert divergent_result["status"] == wal.WAL_CONFLICT
    assert len([event for event in _events(tmp_path) if event.state == wal.EVENT_COMMITTED]) == 1


def test_source_occurrence_register_recovery_reuses_committed_execution_without_new_event(tmp_path):
    source_key = (
        'turtle-paper-register-occurrence:v1:{"setup":"TURTLE20","side":"LONG",'
        '"signal_ts":1700000000,"symbol":"BTCUSDT"}'
    )
    original = _position()
    first = _register(_adapter(tmp_path), original, idempotency_key=source_key)
    assert first.ok is True
    first_events = _events(tmp_path)
    identity = original["execution_id"]

    restarted = _position(entry=111.0, stop=90.0, initial_stop=90.0, tp50=132.0)
    recovered = _register(_adapter(tmp_path), restarted, idempotency_key=source_key)

    assert recovered.ok is True
    assert recovered.write_attempted is False
    assert recovered.write_committed is True
    assert restarted["execution_id"] == restarted["lifecycle_id"] == identity
    assert restarted["entry"] == original["entry"]
    assert restarted["stop"] == original["stop"]
    assert _events(tmp_path) == first_events


def test_read_only_source_occurrence_register_recovers_exact_row_without_new_event(monkeypatch, tmp_path):
    source_key = (
        'turtle-paper-register-occurrence:v1:{"setup":"TURTLE20","side":"LONG",'
        '"signal_ts":1700000000,"symbol":"BTCUSDT"}'
    )
    adapter = _adapter(tmp_path)
    original = _position()
    assert _register(adapter, original, idempotency_key=source_key).ok is True
    committed_before_read = _events(tmp_path)

    def unexpected_identity_or_write(*_args, **_kwargs):
        pytest.fail("read-only REGISTER recovery must not generate or write")

    monkeypatch.setattr(paper, "generate_execution_lifecycle_id", unexpected_identity_or_write)
    monkeypatch.setattr(paper.core, "register_trade_v2", unexpected_identity_or_write)

    recovered = _position(entry=111.0, stop=90.0, initial_stop=90.0, tp50=132.0)
    result = _read_register(adapter, recovered, idempotency_key=source_key)

    assert result.ok is True
    assert result.found is True
    assert result.execution_id == original["execution_id"]
    assert result.mutation_payload is not None
    assert result.mutation_payload["trade"]["execution_id"] == original["execution_id"]
    assert recovered["execution_id"] == recovered["lifecycle_id"] == original["execution_id"]
    assert recovered["entry"] == original["entry"]
    assert recovered["stop"] == original["stop"]
    assert _events(tmp_path) == committed_before_read


def test_read_only_source_occurrence_register_rejects_mismatched_signal_ts(tmp_path):
    source_key = (
        'turtle-paper-register-occurrence:v1:{"setup":"TURTLE20","side":"LONG",'
        '"signal_ts":1700000000,"symbol":"BTCUSDT"}'
    )
    adapter = _adapter(tmp_path)
    assert _register(adapter, _position(), idempotency_key=source_key).ok is True
    before_read = _events(tmp_path)
    mismatched = _position(signal_ts=1_700_000_001, opened_candle_ts=1_700_000_001)

    result = _read_register(adapter, mismatched, idempotency_key=source_key)

    assert result.ok is False
    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID
    assert result.errors == ("committed_register_component_mismatch:signal_ts",)
    assert "execution_id" not in mismatched
    assert _events(tmp_path) == before_read


def test_read_only_source_occurrence_register_rejects_duplicate_source_evidence(monkeypatch, tmp_path):
    source_key = (
        'turtle-paper-register-occurrence:v1:{"setup":"TURTLE20","side":"LONG",'
        '"signal_ts":1700000000,"symbol":"BTCUSDT"}'
    )
    adapter = _adapter(tmp_path)
    assert _register(adapter, _position(), idempotency_key=source_key).ok is True
    before_read = _events(tmp_path)
    original_inspection = paper.wal.inspect_wal_recovery_state

    def duplicate_source_evidence(storage):
        inspection = original_inspection(storage)
        event = next(
            item
            for item in inspection.committed_events
            if item.operation == "REGISTER" and item.idempotency_key == source_key
        )
        duplicate = replace(event, event_id="duplicate-source-evidence")
        return replace(
            inspection,
            committed_events=(event, duplicate),
        )

    monkeypatch.setattr(paper.wal, "inspect_wal_recovery_state", duplicate_source_evidence)
    result = _read_register(adapter, _position(), idempotency_key=source_key)

    assert result.ok is False
    assert result.status == paper.REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID
    assert result.errors == ("register_source_key_not_unique",)
    assert _events(tmp_path) == before_read


def test_read_only_exact_update_and_close_evidence_do_not_append_events(tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True
    position.update(
        {
            "tp50_hit": True,
            "be_moved": True,
            "stop": 100.0,
            "mfe_pct": 5.0,
            "mfe_r": 1.0,
            "candles_to_tp50": 3,
        }
    )
    assert _update(adapter, position, event="TP50", updates={"price": 105.0, "candles_to_tp50": 3}).ok is True
    assert _update(adapter, position, event="BE", updates={"new_sl": 100.0}).ok is True
    before_read_events = _events(tmp_path)
    stale = _position(execution_id=position["execution_id"], lifecycle_id=position["lifecycle_id"])

    tp50 = adapter.read_turtle_paper_committed_update(
        stale,
        event="TP50",
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
    )
    be = adapter.read_turtle_paper_committed_update(
        stale,
        event="BE",
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
    )

    assert tp50.ok is be.ok is True
    assert tp50.found is be.found is True
    assert tp50.mutation_payload["patch"]["price"] == 105.0
    assert be.mutation_payload["patch"]["new_sl"] == 100.0
    assert _events(tmp_path) == before_read_events

    assert _close(adapter, position).ok is True
    before_close_read_events = _events(tmp_path)
    close = adapter.read_turtle_paper_committed_close(
        stale,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
    )

    assert close.ok is True
    assert close.found is True
    assert close.mutation_payload["close"]["factual_economics"] == {
        "close_reason": "TURTLE_EXIT",
        "exit_price": 106.0,
        "pnl_pct": 6.0,
        "realized_r": 1.2,
    }
    assert _events(tmp_path) == before_close_read_events


def test_interprocess_same_logical_distinct_executions_remain_valid(tmp_path):
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    first = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_ONE, "logical-one", 100.0, results),
    )
    second = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_TWO, "logical-two", 100.0, results),
    )
    first.start()
    second.start()
    _join_process(first)
    _join_process(second)

    child_results = [_queue_result(results), _queue_result(results)]
    assert all(item["result"]["ok"] is True for item in child_results)
    document = _document(tmp_path)
    assert sorted(document["open_trades"]) == [_IDENTITY_ONE, _IDENTITY_TWO]
    assert document["indexes"]["by_logical_trade_id"]["TURTLE:TURTLE20:BTCUSDT:LONG"] == [
        _IDENTITY_ONE,
        _IDENTITY_TWO,
    ]


def test_prepared_recovery_state_blocks_a_second_process_without_bypass(tmp_path):
    position = _position()
    adapter = _adapter(tmp_path)
    assert _register(adapter, position).ok is True

    def crash_after_prepared(stage):
        if stage == wal.AFTER_PREPARED:
            raise _CrashInjected(stage)

    with pytest.raises(_CrashInjected):
        _update(adapter, position, updates={"pending": True}, fault_hook=crash_after_prepared)
    snapshot_path, journal_path = _storage_paths(tmp_path)
    before_snapshot = snapshot_path.read_bytes()
    before_journal = journal_path.read_bytes()
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    blocked = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_TWO, "blocked-pending", 100.0, results),
    )
    blocked.start()
    _join_process(blocked)

    result = _queue_result(results)["result"]
    assert result["status"] == paper.REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
    assert result["wal_status"] == wal.PREPARED_PENDING
    assert snapshot_path.read_bytes() == before_snapshot
    assert journal_path.read_bytes() == before_journal


def test_process_termination_releases_os_lock_for_a_later_writer(tmp_path):
    context = multiprocessing.get_context("spawn")
    entered = context.Event()
    release = context.Event()
    holder = context.Process(target=_process_hold_runtime_lock, args=(str(tmp_path), entered, release))
    holder.start()
    assert entered.wait(5)
    holder.terminate()
    holder.join(5)
    assert holder.exitcode is not None

    results = context.Queue()
    writer = context.Process(
        target=_process_register,
        args=(str(tmp_path), _IDENTITY_ONE, "after-crash", 100.0, results),
    )
    writer.start()
    _join_process(writer)

    assert _queue_result(results)["result"]["ok"] is True
    assert [event for event in _events(tmp_path) if event.state == wal.EVENT_COMMITTED]


def test_interprocess_lock_timeout_fails_closed_with_zero_registry_mutation(tmp_path):
    context = multiprocessing.get_context("spawn")
    entered = context.Event()
    release = context.Event()
    holder = context.Process(target=_process_hold_runtime_lock, args=(str(tmp_path), entered, release))
    results = context.Queue()
    contender = context.Process(
        target=_process_register,
        args=(str(tmp_path), None, "timeout-request", 100.0, results),
        kwargs={"timeout_seconds": 0.05},
    )
    try:
        holder.start()
        assert entered.wait(5)
        contender.start()
        _join_process(contender)
    finally:
        release.set()
        _join_process(holder)

    child = _queue_result(results)
    result = child["result"]
    assert result["status"] == paper.REGISTRY_PERSISTENCE_LOCK_TIMEOUT
    assert result["ok"] is False
    assert result["eligible"] is True
    assert result["write_attempted"] is False
    assert result["write_committed"] is False
    assert result["recovery_required"] is False
    assert "execution_id" not in child["position"]
    assert "lifecycle_id" not in child["position"]
    snapshot_path, journal_path = _storage_paths(tmp_path)
    assert not snapshot_path.exists()
    assert not journal_path.exists()
    assert (tmp_path / paper.REGISTRY_V2_PAPER_LOCK_FILENAME).exists()


def test_update_idempotency_key_is_the_current_one_shot_execution_event_pair_only():
    source = Path(paper.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    update = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "update_turtle_paper"
    )
    update_source = ast.get_source_segment(source, update) or ""

    assert 'f"turtle-paper-update:{execution_id}:{event_text}"' in update_source
    assert "management_cycles" not in update_source
    assert "digest" not in update_source
    assert "uuid" not in update_source
    assert "time." not in update_source
    assert "random" not in update_source


def test_adapter_source_guards_keep_core_wal_as_the_only_mutation_boundary():
    source_path = Path(paper.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "core"
    ]
    core_call_names = {node.func.attr for node in calls}

    assert "trade_registry" not in imports
    assert "broker" not in imports
    assert "requests" not in imports
    assert "upstash_redis" not in imports
    assert core_call_names == {"register_trade_v2", "update_trade_v2", "close_trade_v2"}
    assert "partial_close_trade_v2" not in source
    assert "TempWalLock" not in source
    assert "mkdir(" not in source
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "logical_trade_id" not in source[source.index("def update_turtle_paper") : source.index("def close_turtle_paper")]
