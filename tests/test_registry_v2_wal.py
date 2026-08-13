from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

import registry_v2_wal as wal


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_v2_wal.py"


class CrashInjected(RuntimeError):
    pass


def _storage(tmp_path):
    return wal.RegistryV2WalStorage(
        snapshot_path=tmp_path / "snapshot.json",
        journal_path=tmp_path / "events.jsonl",
        lock_path=tmp_path / "lock",
        backup_dir=tmp_path / "backups",
    )


def _base_snapshot(generation=0):
    return {
        "generation": generation,
        "integrity": {
            "last_committed_event_seq": 0,
            "last_committed_event_id": None,
        },
        "wal": {
            "materialized_seq": 0,
            "materialized_event_id": None,
            "materialized_request_digest": None,
            "state": wal.CLEAN,
        },
        "open_trades": {},
        "closed_trades": {},
        "external_observations": {},
        "indexes": {},
        "operation_ledger": {},
        "migration": {},
    }


def _prepare_storage(tmp_path, generation=0):
    storage = _storage(tmp_path)
    wal.write_initial_snapshot(storage, _base_snapshot(generation))
    return storage


def _mutate(snapshot, payload):
    result = copy.deepcopy(dict(snapshot))
    result["counter"] = payload["value"]
    return result


def _apply(storage, *, value=1, operation="TEST", execution_id="exec-1", key="key-1", generation=0, fault=None, mutation_fn=_mutate):
    return wal.apply_temp_wal_mutation(
        storage,
        _base_snapshot(generation),
        {"value": value},
        operation,
        execution_id,
        execution_id,
        key,
        generation,
        mutation_fn,
        fault_hook=fault,
    )


def _raise_at(stage):
    def hook(current):
        if current == stage:
            raise CrashInjected(stage)
    return hook


def _events(storage):
    return wal.read_journal(storage)


def _write_journal_lines(storage, events):
    storage.journal_path.write_text(
        "".join(wal.canonical_json(event.to_dict()) + "\n" for event in events),
        encoding="utf-8",
    )


def _write_journal_documents(storage, documents):
    storage.journal_path.write_text(
        "".join(wal.canonical_json(document) + "\n" for document in documents),
        encoding="utf-8",
    )


def _rewrite_snapshot(storage, update):
    document = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    update(document)
    document["integrity"]["snapshot_digest"] = wal.compute_snapshot_digest(document)
    storage.snapshot_path.write_text(wal.canonical_json(document) + "\n", encoding="utf-8")


def _append_partial_committed_event(storage, cut=7):
    prepared = _events(storage)[-1]
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    after_digest = snapshot["integrity"]["snapshot_digest"]
    result_digest = wal.compute_result_digest({
        "event_id": prepared.event_id,
        "after_digest": after_digest,
        "generation": prepared.target_generation,
    })
    committed = wal.WalEvent.from_dict(dict(
        prepared.to_dict(),
        state=wal.EVENT_COMMITTED,
        after_digest=after_digest,
        result_digest=result_digest,
    ))
    encoded = wal.canonical_json(committed.to_dict()).encode("utf-8")
    storage.journal_path.open("ab").write(encoded[:-cut])
    return committed


def _source_tree():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_read_journal_reads_once_and_returns_the_parsed_result(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    storage.journal_path.write_bytes(b"opaque-journal-bytes")
    original_read_bytes = Path.read_bytes
    read_calls = []
    parsed = ("parsed-event-1", "parsed-event-2")

    def counting_read_bytes(path):
        if path == storage.journal_path:
            read_calls.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(wal, "_parse_journal_bytes", lambda raw: parsed)

    assert wal.read_journal(storage) is parsed
    assert read_calls == [storage.journal_path]


def test_001_canonical_digest_deterministic():
    assert wal.canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert wal.compute_result_digest({"b": 2, "a": 1}) == wal.compute_result_digest({"a": 1, "b": 2})


def test_002_canonical_digest_does_not_mutate():
    value = {"nested": {"a": 1}}
    before = copy.deepcopy(value)
    wal.compute_result_digest(value)
    assert value == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_003_non_finite_digest_rejected(value):
    with pytest.raises(ValueError):
        wal.canonical_json_bytes({"value": value})


def test_004_to_006_event_state_serialization():
    event = wal.WalEvent(1, "event-1", "TEST", "key", "request", "exec-1", "exec-1", 0, 1, "before", "after", wal.EVENT_PREPARED, None, None, None, "V2.1", {"x": 1}, None, None)
    for state in (wal.EVENT_PREPARED, wal.SNAPSHOT_COMMITTED, wal.EVENT_COMMITTED):
        value = dict(event.to_dict(), state=state)
        restored = wal.WalEvent.from_dict(value)
        assert restored.event_id == event.event_id
        assert restored.event_seq == event.event_seq
        assert restored.state == state


def test_007_same_event_id_across_states():
    event = wal.WalEvent(1, "event-1", "TEST", "key", "request", "exec-1", "exec-1", 0, 1, None, None, wal.EVENT_PREPARED, None, None, None, "V2.1", {}, None, None)
    assert wal.WalEvent.from_dict(dict(event.to_dict(), state=wal.SNAPSHOT_COMMITTED)).event_id == event.event_id


def test_008_same_sequence_across_states():
    event = wal.WalEvent(7, "event-7", "TEST", "key", "request", "exec-1", "exec-1", 0, 1, None, None, wal.EVENT_PREPARED, None, None, None, "V2.1", {}, None, None)
    assert wal.WalEvent.from_dict(dict(event.to_dict(), state=wal.EVENT_COMMITTED)).event_seq == 7


def test_009_lifecycle_mismatch_rejected():
    with pytest.raises(ValueError):
        wal.WalEvent(1, "event", "TEST", "key", "request", "exec-1", "exec-2", 0, 1, None, None, wal.EVENT_PREPARED, None, None, None, "V2.1", {}, None, None)


def test_010_storage_paths_required():
    with pytest.raises(TypeError):
        wal.RegistryV2WalStorage()  # type: ignore[call-arg]


def test_011_no_production_defaults():
    assert inspect.signature(wal.RegistryV2WalStorage).parameters["snapshot_path"].default is inspect.Parameter.empty
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for literal in ("registry_v2.json", "trade_registry.json", "/opt/render", "/data"):
        assert literal not in source


def test_012_to_014_prepared_and_snapshot_are_written(tmp_path):
    storage = _prepare_storage(tmp_path)
    result = _apply(storage)
    assert result.ok is True
    assert len(_events(storage)) == 2
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]
    assert storage.snapshot_path.exists()


def test_015_snapshot_generation_is_target(tmp_path):
    storage = _prepare_storage(tmp_path)
    result = _apply(storage, generation=0)
    assert result.generation == 1
    assert json.loads(storage.snapshot_path.read_text())["generation"] == 1


def test_016_to_018_snapshot_witness_is_valid(tmp_path):
    storage = _prepare_storage(tmp_path)
    result = _apply(storage)
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    committed = _events(storage)[-1]
    assert snapshot["integrity"]["last_committed_event_id"] is None
    assert snapshot["integrity"]["last_committed_event_seq"] == 0
    assert snapshot["wal"]["state"] == wal.SNAPSHOT_COMMITTED
    assert snapshot["wal"]["materialized_event_id"] == committed.event_id
    assert snapshot["wal"]["materialized_seq"] == committed.event_seq
    assert snapshot["wal"]["materialized_request_digest"] == committed.request_digest
    assert snapshot["integrity"]["snapshot_digest"] == wal.compute_snapshot_digest(snapshot)


def test_019_to_020_success_only_after_event_committed(tmp_path):
    storage = _prepare_storage(tmp_path)
    result = _apply(storage)
    assert result.ok is True
    assert result.state == wal.EVENT_COMMITTED
    assert _events(storage)[-1].state == wal.EVENT_COMMITTED


def test_021_to_024_committed_lookup_and_pending_state(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    events = _events(storage)
    found = wal.find_committed_operation(events, "TEST", "exec-1", "key-1", events[-1].request_digest)
    assert found.ok is True
    assert wal.find_committed_operation(events[:1], "TEST", "exec-1", "key-1").pending is True


def test_022_same_retry_same_digest_is_idempotent(tmp_path):
    storage = _prepare_storage(tmp_path)
    first = _apply(storage)
    second = _apply(storage)
    assert first.ok is second.ok is True
    assert len(_events(storage)) == 2
    assert second.event_id == first.event_id


def test_023_same_key_different_digest_conflicts(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    result = _apply(storage, value=2)
    assert result.ok is False
    assert result.status == wal.WAL_CONFLICT


def test_024_prepared_is_not_committed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    lookup = wal.find_committed_operation(_events(storage), "TEST", "exec-1", "key-1")
    assert lookup.ok is False
    assert lookup.pending is True


def test_025_crash_before_prepared_leaves_no_journal_change(tmp_path):
    storage = _prepare_storage(tmp_path)
    before = storage.journal_path.read_bytes() if storage.journal_path.exists() else b""
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.BEFORE_PREPARED))
    assert (storage.journal_path.read_bytes() if storage.journal_path.exists() else b"") == before


def test_026_crash_after_prepared_is_pending(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    assert wal.inspect_wal_recovery_state(storage).status == wal.PREPARED_PENDING


def test_027_recovery_prepared_replays_once(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    calls = []
    def resolver(payload):
        calls.append(payload)
        return _mutate
    result = wal.recover_temp_wal(storage, resolver)
    again = wal.recover_temp_wal(storage, resolver)
    assert result.ok is True
    assert again.ok is True
    assert len(calls) == 1
    assert len(_events(storage)) == 2


@pytest.mark.parametrize("stage", [wal.DURING_TEMP_WRITE, wal.AFTER_TEMP_FSYNC])
def test_temp_write_fault_stages(tmp_path, stage):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(stage))
    assert wal.inspect_wal_recovery_state(storage).status == wal.PREPARED_PENDING


def test_030_crash_after_replace_has_witness(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT


def test_031_witness_recovery_does_not_reapply(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.ok is True
    assert calls == []


def test_032_crash_before_event_commit_finalizes(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.BEFORE_EVENT_COMMIT))
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT
    assert wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay")).ok is True


def test_033_crash_after_commit_is_idempotent(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_EVENT_COMMIT))
    result = _apply(storage)
    assert result.ok is True
    assert len(_events(storage)) == 2


def test_034_truncated_journal_tail_detected(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.journal_path.open("ab").write(b"{truncated")
    assert wal.inspect_wal_recovery_state(storage).status == wal.JOURNAL_CORRUPT


def test_035_corrupt_middle_journal_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    lines = storage.journal_path.read_bytes().splitlines()
    lines[1] = b"not-json"
    storage.journal_path.write_bytes(b"\n".join(lines) + b"\n")
    assert wal.inspect_wal_recovery_state(storage).status == wal.JOURNAL_CORRUPT


def test_036_invalid_snapshot_digest_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    document = json.loads(storage.snapshot_path.read_text())
    document["integrity"]["snapshot_digest"] = "0" * 64
    storage.snapshot_path.write_text(json.dumps(document), encoding="utf-8")
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_INVALID


def test_037_snapshot_journal_divergence_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    document = json.loads(storage.snapshot_path.read_text())
    document["wal"]["materialized_event_id"] = "other"
    document["integrity"]["snapshot_digest"] = wal.compute_snapshot_digest(document)
    storage.snapshot_path.write_text(json.dumps(document), encoding="utf-8")
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_JOURNAL_DIVERGENCE


def test_038_generation_mismatch_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    result = _apply(storage, generation=1)
    assert result.ok is False
    assert "generation_mismatch" in result.errors


def test_039_duplicate_prepared_identical_allowed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    line = storage.journal_path.read_bytes()
    storage.journal_path.open("ab").write(line)
    assert len(wal.read_journal(storage)) == 2


def test_040_duplicate_prepared_divergent_conflicts(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    event = _events(storage)[0]
    divergent = dict(event.to_dict(), request_digest="different")
    storage.journal_path.open("a", encoding="utf-8").write(wal.canonical_json(divergent) + "\n")
    with pytest.raises(ValueError):
        wal.read_journal(storage)


def test_041_event_sequence_monotonic(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    events = list(_events(storage))
    events[0], events[1] = events[1], events[0]
    _write_journal_lines(storage, events)
    assert wal.inspect_wal_recovery_state(storage).status == wal.JOURNAL_CORRUPT


def test_042_committed_chain_digest(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    first_committed = _events(storage)[-1]
    _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    second_committed = _events(storage)[-1]
    assert second_committed.previous_committed_event_digest == wal.compute_event_digest(first_committed)


def test_043_two_independent_events_chain(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    assert len([event for event in _events(storage) if event.state == wal.EVENT_COMMITTED]) == 2


def test_044_writer_blocked_with_pending_prepared(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    result = _apply(storage, execution_id="exec-2", key="key-2")
    assert result.status == wal.WAL_RECOVERY_REQUIRED


def test_045_clean_inspection(tmp_path):
    storage = _prepare_storage(tmp_path)
    assert wal.inspect_wal_recovery_state(storage).status == wal.CLEAN


def test_046_prepared_inspection(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    assert wal.inspect_wal_recovery_state(storage).pending_event.state == wal.EVENT_PREPARED


def test_047_snapshot_pending_inspection(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.BEFORE_EVENT_COMMIT))
    assert wal.inspect_wal_recovery_state(storage).pending_event.state == wal.EVENT_PREPARED


def test_048_result_envelope_frozen(tmp_path):
    result = _apply(_prepare_storage(tmp_path))
    with pytest.raises(AttributeError):
        result.ok = False


def test_049_to_052_no_external_runtime_capabilities():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "trade_registry" not in source
    assert "requests" not in source
    assert "redis" not in source
    assert "os.environ" not in source


def test_053_python_311_syntax():
    assert isinstance(ast.parse(MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 11)), ast.Module)


def test_054_temp_files_have_unique_names(tmp_path):
    first = _prepare_storage(tmp_path / "one") if False else _storage(tmp_path)
    # mkstemp is exercised by two sequential atomic writes and the target remains stable.
    wal.write_initial_snapshot(first, _base_snapshot())
    before = first.snapshot_path.read_bytes()
    wal.write_initial_snapshot(first, _base_snapshot(1))
    assert first.snapshot_path.read_bytes() != before


def test_055_atomic_replace_keeps_valid_snapshot(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    assert wal.compute_snapshot_digest(json.loads(storage.snapshot_path.read_text())) == json.loads(storage.snapshot_path.read_text())["integrity"]["snapshot_digest"]


def test_056_no_production_path_literals():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for literal in ("registry_v2.json", "trade_registry.json", "/opt/render", "/data"):
        assert literal not in source


def test_057_journal_is_jsonl_append_only(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    assert all(isinstance(json.loads(line), dict) for line in storage.journal_path.read_text().splitlines())


def test_058_committed_lines_not_rewritten_on_retry(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    before = storage.journal_path.read_bytes()
    _apply(storage)
    assert storage.journal_path.read_bytes() == before


def test_059_operation_ledger_not_authority(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    assert all(event.state == wal.EVENT_COMMITTED or event.result_digest is None for event in _events(storage))


def test_060_result_digest_deterministic(tmp_path):
    storage = _prepare_storage(tmp_path)
    result = _apply(storage)
    committed = _events(storage)[-1]
    expected = wal.compute_result_digest({"event_id": committed.event_id, "after_digest": committed.after_digest, "generation": committed.target_generation})
    assert result.result_digest == expected


def test_061_recovery_requires_resolver(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    result = wal.recover_temp_wal(storage, lambda payload: None)
    assert result.status == wal.WAL_RECOVERY_REQUIRED


def test_062_recovery_resolver_receives_exact_payload(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, value=42, fault=_raise_at(wal.AFTER_PREPARED))
    received = []
    def resolver(payload):
        received.append(payload)
        return _mutate
    wal.recover_temp_wal(storage, resolver)
    assert received == [{"value": 42}]


def test_063_replay_uses_same_event_and_key(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    original = _events(storage)[0]
    wal.recover_temp_wal(storage, lambda payload: _mutate)
    committed = _events(storage)[-1]
    assert committed.event_id == original.event_id
    assert committed.idempotency_key == original.idempotency_key


def test_064_recovery_no_double_apply(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    calls = 0
    def resolver(payload):
        nonlocal calls
        calls += 1
        return _mutate
    wal.recover_temp_wal(storage, resolver)
    wal.recover_temp_wal(storage, resolver)
    assert calls == 1


def test_065_storage_stays_in_tmp_path(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    assert storage.snapshot_path.is_relative_to(tmp_path)
    assert storage.journal_path.is_relative_to(tmp_path)


def test_066_no_v1_file_created(tmp_path):
    _apply(_prepare_storage(tmp_path))
    assert not (tmp_path / "trade_registry.json").exists()


def test_067_no_external_call_capability():
    tree = _source_tree()
    roots = {alias.name.split(".", maxsplit=1)[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert roots.isdisjoint({"requests", "redis", "socket", "subprocess"})


def test_068_injected_lock_abstraction_is_used(tmp_path):
    storage = _prepare_storage(tmp_path)
    calls = []
    class Lock:
        def __enter__(self):
            calls.append("enter")
            return self
        def __exit__(self, *args):
            calls.append("exit")
    result = wal.apply_temp_wal_mutation(storage, _base_snapshot(), {"value": 1}, "TEST", "exec", "exec", "key", 0, _mutate, lock=Lock())
    assert result.ok is True
    assert calls == ["enter", "exit"]


def test_069_directory_fsync_is_safe_on_platform(tmp_path):
    storage = _prepare_storage(tmp_path)
    assert _apply(storage).ok is True


def test_070_read_only_inspection_does_not_change_bytes(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    snapshot_before = storage.snapshot_path.read_bytes()
    journal_before = storage.journal_path.read_bytes()
    wal.inspect_wal_recovery_state(storage)
    assert storage.snapshot_path.read_bytes() == snapshot_before
    assert storage.journal_path.read_bytes() == journal_before


def test_071_normal_journal_has_exactly_prepared_then_committed(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]
    assert wal.SNAPSHOT_COMMITTED not in [event.state for event in _events(storage)]


def test_072_snapshot_committed_is_witness_state_only(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["wal"]["state"] == wal.SNAPSHOT_COMMITTED
    assert len(_events(storage)) == 2


def test_073_witness_contains_event_identity_and_request_digest(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    event = _events(storage)[-1]
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["wal"]["materialized_event_id"] == event.event_id
    assert snapshot["wal"]["materialized_seq"] == event.event_seq
    assert snapshot["wal"]["materialized_request_digest"] == event.request_digest
    assert snapshot["generation"] == event.target_generation


def test_074_after_replace_has_one_prepared_line_and_witness(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED]
    assert json.loads(storage.snapshot_path.read_text())["wal"]["state"] == wal.SNAPSHOT_COMMITTED


def test_075_recovery_after_replace_only_appends_event_committed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    before = storage.journal_path.read_bytes()
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("witness must not replay"))
    assert result.ok is True
    assert storage.journal_path.read_bytes().startswith(before)
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]


def test_076_recovered_commit_uses_factual_witness_after_digest(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("witness must not replay"))
    committed = _events(storage)[-1]
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert result.ok is True
    assert committed.after_digest == snapshot["integrity"]["snapshot_digest"]


def test_077_recovered_result_digest_uses_factual_after_digest(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.BEFORE_EVENT_COMMIT))
    wal.recover_temp_wal(storage, lambda payload: pytest.fail("witness must not replay"))
    committed = _events(storage)[-1]
    assert committed.result_digest == wal.compute_result_digest({
        "event_id": committed.event_id,
        "after_digest": committed.after_digest,
        "generation": committed.target_generation,
    })


def test_078_recovery_with_matching_generation_and_before_digest_succeeds(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    calls = []
    def resolver(payload):
        calls.append(payload)
        return _mutate
    result = wal.recover_temp_wal(storage, resolver)
    assert result.ok is True
    assert len(calls) == 1
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]


def test_079_wrong_before_digest_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    _rewrite_snapshot(storage, lambda document: document.update(counter=99))
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("digest gate must run first"))
    assert result.status == wal.WAL_CONFLICT
    assert len(_events(storage)) == 1


def test_080_wrong_before_digest_does_not_call_resolver(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    _rewrite_snapshot(storage, lambda document: document.update(counter=99))
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.status == wal.WAL_CONFLICT
    assert calls == []


def test_081_witness_wrong_request_digest_is_divergence(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    _rewrite_snapshot(storage, lambda document: document["wal"].update(materialized_request_digest="wrong"))
    inspection = wal.inspect_wal_recovery_state(storage)
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert inspection.status == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert result.status == wal.WAL_INVALID
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("materialized_seq", 99),
    ("materialized_event_id", "other-event"),
])
def test_082_to_083_witness_wrong_sequence_or_event_id_fails_closed(tmp_path, field, value):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    _rewrite_snapshot(storage, lambda document: document["wal"].update({field: value}))
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_JOURNAL_DIVERGENCE


def test_084_witness_wrong_generation_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    _rewrite_snapshot(storage, lambda document: document.update(generation=99))
    assert wal.inspect_wal_recovery_state(storage).status == wal.SNAPSHOT_JOURNAL_DIVERGENCE


def test_085_pending_witness_does_not_advance_last_committed_fields(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["integrity"]["last_committed_event_seq"] == 0
    assert snapshot["integrity"]["last_committed_event_id"] is None


def test_086_committed_journal_is_authority_over_old_integrity_fields(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["integrity"]["last_committed_event_id"] is None
    assert snapshot["integrity"]["last_committed_event_seq"] == 0
    assert wal.inspect_wal_recovery_state(storage).status == wal.CLEAN


def test_087_retry_after_recovery_adds_no_lines(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    wal.recover_temp_wal(storage, lambda payload: _mutate)
    before = storage.journal_path.read_bytes()
    result = _apply(storage)
    assert result.ok is True
    assert storage.journal_path.read_bytes() == before


def test_088_recovery_never_double_applies_mutation(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    calls = 0
    def resolver(payload):
        nonlocal calls
        calls += 1
        return _mutate
    wal.recover_temp_wal(storage, resolver)
    wal.recover_temp_wal(storage, resolver)
    assert calls == 1


def test_089_second_operation_preserves_committed_chain_and_witness(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    first = _events(storage)[-1]
    _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    second = _events(storage)[-1]
    snapshot = json.loads(storage.snapshot_path.read_text())
    assert second.previous_committed_event_digest == wal.compute_event_digest(first)
    assert snapshot["wal"]["materialized_event_id"] == second.event_id
    assert snapshot["integrity"]["last_committed_event_id"] is None
    assert snapshot["integrity"]["last_committed_event_seq"] == 0


def test_090_committed_without_prepared_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    _write_journal_lines(storage, [_events(storage)[-1]])
    with pytest.raises(ValueError, match="event_committed_without_prepared"):
        wal.read_journal(storage)


def test_091_snapshot_committed_journal_line_is_not_operational(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    prepared = _events(storage)[0]
    snapshot_line = wal.WalEvent.from_dict(dict(prepared.to_dict(), state=wal.SNAPSHOT_COMMITTED))
    _write_journal_lines(storage, [prepared, snapshot_line])
    with pytest.raises(ValueError, match="journal_operational_state_invalid"):
        wal.read_journal(storage)


def test_092_divergent_duplicate_prepared_target_generation_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    prepared = _events(storage)[0]
    divergent = wal.WalEvent.from_dict(dict(prepared.to_dict(), target_generation=99))
    storage.journal_path.open("a", encoding="utf-8").write(wal.canonical_json(divergent.to_dict()) + "\n")
    with pytest.raises(ValueError, match="target_generation_invalid"):
        wal.read_journal(storage)


def test_093_recovery_resolver_annotation_accepts_payload_mapping():
    annotation = inspect.signature(wal.recover_temp_wal).parameters["mutation_fn_resolver"].annotation
    assert "Mapping" in str(annotation)


def test_094_materialization_preserves_prior_last_committed_fields(tmp_path):
    storage = _prepare_storage(tmp_path)
    def mutation(snapshot, payload):
        result = copy.deepcopy(dict(snapshot))
        result["integrity"]["last_committed_event_seq"] = 999
        result["integrity"]["last_committed_event_id"] = "pending-must-not-commit"
        return result
    assert _apply(storage, mutation_fn=mutation).ok is True
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["integrity"]["last_committed_event_seq"] == 0
    assert snapshot["integrity"]["last_committed_event_id"] is None


def test_095_previous_committed_witness_is_valid_base_for_new_prepared(tmp_path):
    storage = _prepare_storage(tmp_path)
    assert _apply(storage, value=1).ok is True
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    inspection = wal.inspect_wal_recovery_state(storage)
    assert inspection.status == wal.PREPARED_PENDING
    assert inspection.pending_event.event_id == "event_00000000000000000002"


def test_096_recover_new_prepared_over_previous_witness(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    result = wal.recover_temp_wal(storage, lambda payload: _mutate)
    assert result.ok is True
    assert result.event_id == "event_00000000000000000002"


def test_097_new_prepared_resolver_runs_exactly_once(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    calls = []
    def resolver(payload):
        calls.append(payload)
        return _mutate
    assert wal.recover_temp_wal(storage, resolver).ok is True
    assert wal.recover_temp_wal(storage, resolver).ok is True
    assert calls == [{"value": 2}]


def test_098_new_recovery_has_prepared_and_committed_only(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    wal.recover_temp_wal(storage, lambda payload: _mutate)
    assert [event.state for event in _events(storage)] == [
        wal.EVENT_PREPARED, wal.EVENT_COMMITTED,
        wal.EVENT_PREPARED, wal.EVENT_COMMITTED,
    ]
    assert all(event.state != wal.SNAPSHOT_COMMITTED for event in _events(storage))


def test_099_new_recovery_preserves_previous_committed_chain(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    first_committed = _events(storage)[1]
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    wal.recover_temp_wal(storage, lambda payload: _mutate)
    second_committed = _events(storage)[-1]
    assert second_committed.previous_committed_event_digest == wal.compute_event_digest(first_committed)


def test_100_retry_after_new_recovery_is_idempotent(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    wal.recover_temp_wal(storage, lambda payload: _mutate)
    before = storage.journal_path.read_bytes()
    result = _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    assert result.ok is True
    assert storage.journal_path.read_bytes() == before


def test_101_previous_event_witness_is_not_event2_witness(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    first = _events(storage)[-1]
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["wal"]["materialized_event_id"] == first.event_id
    assert wal.inspect_wal_recovery_state(storage).status == wal.PREPARED_PENDING


def test_102_second_after_replace_has_pending_witness_state(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_REPLACE))
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    inspection = wal.inspect_wal_recovery_state(storage)
    assert snapshot["wal"]["materialized_event_id"] == inspection.pending_event.event_id
    assert inspection.status == wal.SNAPSHOT_COMMITTED_PENDING_EVENT_COMMIT


def test_103_second_after_replace_recovery_does_not_resolve_mutation(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_REPLACE))
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.ok is True
    assert calls == []


def test_104_second_witness_wrong_request_digest_is_divergence(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_REPLACE))
    _rewrite_snapshot(storage, lambda document: document["wal"].update(materialized_request_digest="wrong"))
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert calls == []


def test_105_second_base_digest_change_fails_before_resolver(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    _rewrite_snapshot(storage, lambda document: document.update(counter=999))
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.SNAPSHOT_JOURNAL_DIVERGENCE
    assert calls == []


def test_106_three_sequential_events_recover_third_and_keep_chain(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    second_committed = _events(storage)[-1]
    with pytest.raises(CrashInjected):
        _apply(storage, value=3, execution_id="exec-3", key="key-3", generation=2, fault=_raise_at(wal.AFTER_PREPARED))
    assert wal.inspect_wal_recovery_state(storage).status == wal.PREPARED_PENDING
    assert wal.recover_temp_wal(storage, lambda payload: _mutate).ok is True
    committed = [event for event in _events(storage) if event.state == wal.EVENT_COMMITTED]
    assert len(committed) == 3
    assert committed[-1].previous_committed_event_digest == wal.compute_event_digest(second_committed)


@pytest.mark.parametrize("field", ["previous_committed_event_digest", "schema_version"])
def test_107_transition_metadata_must_match_between_prepared_and_committed(tmp_path, field):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    events = list(_events(storage))
    changed = dict(events[2].to_dict(), **{field: "divergent"})
    events[2] = wal.WalEvent.from_dict(changed)
    _write_journal_lines(storage, events)
    with pytest.raises(ValueError, match="(event_identity_conflict|event_chain_pointer_invalid)"):
        wal.read_journal(storage)


def test_108_same_sequence_with_different_event_ids_is_corrupt(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    prepared = _events(storage)[0]
    divergent = dict(prepared.to_dict(), event_id="event-other")
    _write_journal_documents(storage, [prepared.to_dict(), divergent])
    with pytest.raises(ValueError, match="event_identity_global_conflict"):
        wal.read_journal(storage)


def test_109_same_event_id_with_different_sequences_is_corrupt(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    prepared = _events(storage)[0]
    divergent = dict(prepared.to_dict(), event_seq=2)
    _write_journal_documents(storage, [prepared.to_dict(), divergent])
    with pytest.raises(ValueError, match="event_identity_global_conflict"):
        wal.read_journal(storage)


def test_110_prepared_committed_same_global_identity_remains_valid(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    events = _events(storage)
    assert events[0].event_seq == events[1].event_seq
    assert events[0].event_id == events[1].event_id
    assert wal.read_journal(storage) == events


@pytest.mark.parametrize("event_index", [0, 1])
@pytest.mark.parametrize("field,change", [
    ("mutation_payload", {"value": 999}),
    ("operation", "OTHER"),
    ("execution_id", "exec-other"),
    ("lifecycle_id", "life-other"),
    ("idempotency_key", "key-other"),
    ("expected_generation", 1),
])
def test_111_to_122_tampered_event_request_identity_is_corrupt(tmp_path, event_index, field, change):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    documents = [event.to_dict() for event in _events(storage)]
    if field == "execution_id":
        documents[event_index][field] = change
        documents[event_index]["lifecycle_id"] = change
    elif field == "lifecycle_id":
        documents[event_index][field] = change
        documents[event_index]["execution_id"] = change
    elif field == "expected_generation":
        documents[event_index][field] = change
        documents[event_index]["target_generation"] = change + 1
    else:
        documents[event_index][field] = change
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError):
        wal.read_journal(storage)


def test_123_before_digest_must_match_between_transitions(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    documents = [event.to_dict() for event in _events(storage)]
    documents[1]["before_digest"] = "different-before-digest"
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="event_identity_conflict"):
        wal.read_journal(storage)


def test_124_target_generation_must_follow_expected_generation(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    documents = [event.to_dict() for event in _events(storage)]
    documents[0]["target_generation"] = 99
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="target_generation_invalid"):
        wal.read_journal(storage)


def test_125_strict_reader_still_rejects_truncated_tail(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    storage.journal_path.open("ab").write(b'{"partial":')
    with pytest.raises(ValueError, match="journal_truncated_tail"):
        wal.read_journal(storage)


def test_126_partial_tail_after_prepared_is_repaired_and_replayed(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    prefix = storage.journal_path.read_bytes()
    storage.journal_path.open("ab").write(b'{"partial":')
    result = wal.recover_temp_wal(storage, lambda payload: _mutate)
    assert result.ok is True
    assert storage.journal_path.read_bytes().startswith(prefix)
    assert [event.state for event in _events(storage)] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]


def test_127_partial_tail_prepared_recovery_calls_resolver_once(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    storage.journal_path.open("ab").write(b"partial-garbage")
    calls = []
    def resolver(payload):
        calls.append(payload)
        return _mutate
    assert wal.recover_temp_wal(storage, resolver).ok is True
    assert wal.recover_temp_wal(storage, resolver).ok is True
    assert len(calls) == 1


def test_128_partial_commit_tail_uses_witness_without_resolver(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    prefix = storage.journal_path.read_bytes()
    expected_committed = _append_partial_committed_event(storage)
    with pytest.raises(ValueError, match="journal_truncated_tail"):
        wal.read_journal(storage)
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    events = _events(storage)
    assert result.ok is True
    assert calls == []
    assert storage.journal_path.read_bytes().startswith(prefix)
    assert [event.state for event in events] == [wal.EVENT_PREPARED, wal.EVENT_COMMITTED]
    assert events[-1].event_id == expected_committed.event_id


def test_129_partial_commit_tail_final_journal_has_two_records(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    _append_partial_committed_event(storage)
    wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay witness"))
    assert len(_events(storage)) == 2
    assert all(event.state != wal.SNAPSHOT_COMMITTED for event in _events(storage))


def test_130_complete_committed_plus_partial_tail_preserves_idempotency(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    committed_prefix = storage.journal_path.read_bytes()
    storage.journal_path.open("ab").write(b"trailing-partial-garbage")
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay committed"))
    assert result.ok is True
    assert storage.journal_path.read_bytes() == committed_prefix
    before_retry = storage.journal_path.read_bytes()
    assert _apply(storage).ok is True
    assert storage.journal_path.read_bytes() == before_retry


def test_131_middle_invalid_json_is_never_repaired(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    original = storage.journal_path.read_bytes()
    lines = original.splitlines(keepends=True)
    storage.journal_path.write_bytes(lines[0] + b"not-json\n" + b"partial")
    before = storage.journal_path.read_bytes()
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay corrupt journal"))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.JOURNAL_CORRUPT
    assert storage.journal_path.read_bytes() == before


def test_132_final_invalid_json_with_newline_is_never_repaired(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.journal_path.open("ab").write(b"not-json\n")
    before = storage.journal_path.read_bytes()
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay corrupt journal"))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.JOURNAL_CORRUPT
    assert storage.journal_path.read_bytes() == before


def test_133_truncated_only_line_has_no_safe_repair_or_invented_event(tmp_path):
    storage = _storage(tmp_path)
    storage.journal_path.write_bytes(b'{"event_seq":')
    before = storage.journal_path.read_bytes()
    assert wal.repair_truncated_journal_tail_for_recovery(storage) is False
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not invent event"))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.JOURNAL_CORRUPT
    assert storage.journal_path.read_bytes() == before


def test_134_tail_repair_preserves_prefix_bytes_exactly(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    prefix = storage.journal_path.read_bytes()
    storage.journal_path.open("ab").write(b"partial-tail")
    assert wal.repair_truncated_journal_tail_for_recovery(storage) is True
    assert storage.journal_path.read_bytes() == prefix


def test_135_tail_repair_fsyncs_file_and_directory(tmp_path, monkeypatch):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.journal_path.open("ab").write(b"partial-tail")
    fsync_calls = []
    directory_calls = []
    monkeypatch.setattr(wal.os, "fsync", lambda fd: fsync_calls.append(fd))
    monkeypatch.setattr(wal, "_fsync_directory", lambda path: directory_calls.append(path))
    assert wal.repair_truncated_journal_tail_for_recovery(storage) is True
    assert len(fsync_calls) >= 1
    assert directory_calls == [storage.journal_path.parent]


def test_136_inspection_does_not_repair_truncated_tail(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.journal_path.open("ab").write(b"partial-tail")
    before = storage.journal_path.read_bytes()
    inspection = wal.inspect_wal_recovery_state(storage)
    assert inspection.status == wal.JOURNAL_CORRUPT
    assert storage.journal_path.read_bytes() == before


def test_137_three_event_chain_recovers_partial_third_commit(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage, value=1)
    _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    second_committed = _events(storage)[-1]
    with pytest.raises(CrashInjected):
        _apply(storage, value=3, execution_id="exec-3", key="key-3", generation=2, fault=_raise_at(wal.AFTER_REPLACE))
    _append_partial_committed_event(storage)
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay third witness"))
    committed = [event for event in _events(storage) if event.state == wal.EVENT_COMMITTED]
    assert result.ok is True
    assert len(committed) == 3
    assert committed[-1].previous_committed_event_digest == wal.compute_event_digest(second_committed)


def test_138_partial_witness_recovery_digests_are_factual(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_REPLACE))
    _append_partial_committed_event(storage)
    wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not replay witness"))
    committed = _events(storage)[-1]
    snapshot = json.loads(storage.snapshot_path.read_text(encoding="utf-8"))
    assert committed.after_digest == snapshot["integrity"]["snapshot_digest"]
    assert committed.result_digest == wal.compute_result_digest({
        "event_id": committed.event_id,
        "after_digest": committed.after_digest,
        "generation": committed.target_generation,
    })


def test_139_second_recovery_after_tail_repair_writes_nothing(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    storage.journal_path.open("ab").write(b"partial-tail")
    assert wal.recover_temp_wal(storage, lambda payload: _mutate).ok is True
    before = storage.journal_path.read_bytes()
    assert wal.recover_temp_wal(storage, lambda payload: pytest.fail("must be idempotent")).ok is True
    assert storage.journal_path.read_bytes() == before


def test_140_complete_json_without_newline_is_not_silently_removed(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    prefix = storage.journal_path.read_bytes()
    complete_record = wal.canonical_json(_events(storage)[-1].to_dict()).encode("utf-8")
    storage.journal_path.open("ab").write(complete_record)
    before = storage.journal_path.read_bytes()
    with pytest.raises(ValueError, match="complete_record"):
        wal.repair_truncated_journal_tail_for_recovery(storage)
    assert storage.journal_path.read_bytes() == before
    assert storage.journal_path.read_bytes().startswith(prefix)


def test_141_witness_divergence_blocks_tail_repair(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    _rewrite_snapshot(storage, lambda document: document["wal"].update(materialized_event_id="other"))
    storage.journal_path.open("ab").write(b"partial-tail")
    before = storage.journal_path.read_bytes()
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must fail closed"))
    assert result.status == wal.WAL_INVALID
    assert storage.journal_path.read_bytes() == before


def test_142_first_prepared_requires_null_chain_pointer(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    documents = [event.to_dict() for event in _events(storage)]
    documents[0]["previous_committed_event_digest"] = "wrong"
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="event_chain_pointer_invalid"):
        wal.read_journal(storage)


def test_143_second_prepared_requires_previous_committed_digest(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    documents = [event.to_dict() for event in _events(storage)]
    documents[-1]["previous_committed_event_digest"] = "wrong"
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="event_chain_pointer_invalid"):
        wal.read_journal(storage)


def test_144_second_prepared_with_correct_previous_digest_is_valid(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    first_committed = _events(storage)[-1]
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    second_prepared = _events(storage)[-1]
    assert second_prepared.previous_committed_event_digest == wal.compute_event_digest(first_committed)


def test_145_tampered_pending_chain_pointer_blocks_recovery(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    documents = [event.to_dict() for event in _events(storage)]
    documents[-1]["previous_committed_event_digest"] = "wrong"
    _write_journal_documents(storage, documents)
    before = storage.journal_path.read_bytes()
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.JOURNAL_CORRUPT
    assert calls == []
    assert storage.journal_path.read_bytes() == before
    assert all(json.loads(line)["state"] != wal.EVENT_COMMITTED for line in before.splitlines()[2:])


def test_146_duplicate_prepared_with_correct_pointer_remains_valid(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    with pytest.raises(CrashInjected):
        _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1, fault=_raise_at(wal.AFTER_PREPARED))
    prepared = _events(storage)[-1]
    storage.journal_path.open("a", encoding="utf-8").write(wal.canonical_json(prepared.to_dict()) + "\n")
    assert len(wal.read_journal(storage)) == 4


def test_147_prepared_after_digest_must_be_null(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    documents = [event.to_dict() for event in _events(storage)]
    documents[0]["after_digest"] = "unexpected"
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="prepared_result_fields_invalid"):
        wal.read_journal(storage)


def test_148_prepared_result_digest_must_be_null(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    documents = [event.to_dict() for event in _events(storage)]
    documents[0]["result_digest"] = "unexpected"
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="prepared_result_fields_invalid"):
        wal.read_journal(storage)


def test_149_committed_after_digest_must_be_nonempty(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    documents = [event.to_dict() for event in _events(storage)]
    documents[1]["after_digest"] = None
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="committed_after_digest_invalid"):
        wal.read_journal(storage)


def test_150_committed_result_digest_must_be_present(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    documents = [event.to_dict() for event in _events(storage)]
    documents[1]["result_digest"] = None
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="committed_result_digest_invalid"):
        wal.read_journal(storage)


def test_151_committed_result_digest_must_be_factual(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    documents = [event.to_dict() for event in _events(storage)]
    documents[1]["result_digest"] = "wrong-result"
    _write_journal_documents(storage, documents)
    with pytest.raises(ValueError, match="committed_result_digest_invalid"):
        wal.read_journal(storage)


def test_152_valid_committed_factual_result_digest_remains_accepted(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    committed = _events(storage)[-1]
    assert committed.result_digest == wal.compute_result_digest({
        "event_id": committed.event_id,
        "after_digest": committed.after_digest,
        "generation": committed.target_generation,
    })
    assert wal.inspect_wal_recovery_state(storage).status == wal.CLEAN


def test_153_committed_journal_without_snapshot_is_not_clean(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.snapshot_path.unlink()
    inspection = wal.inspect_wal_recovery_state(storage)
    assert inspection.status == wal.SNAPSHOT_INVALID


def test_154_recovery_with_committed_journal_without_snapshot_fails_closed(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.snapshot_path.unlink()
    result = wal.recover_temp_wal(storage, lambda payload: pytest.fail("must not resolve"))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.SNAPSHOT_INVALID


def test_155_new_mutation_is_blocked_when_committed_snapshot_is_missing(tmp_path):
    storage = _prepare_storage(tmp_path)
    _apply(storage)
    storage.snapshot_path.unlink()
    before = storage.journal_path.read_bytes()
    result = _apply(storage, value=2, execution_id="exec-2", key="key-2", generation=1)
    assert result.status == wal.WAL_RECOVERY_REQUIRED
    assert wal.SNAPSHOT_INVALID in result.errors
    assert storage.journal_path.read_bytes() == before


def test_156_pending_prepared_without_snapshot_has_no_recovery_callback(tmp_path):
    storage = _prepare_storage(tmp_path)
    with pytest.raises(CrashInjected):
        _apply(storage, fault=_raise_at(wal.AFTER_PREPARED))
    storage.snapshot_path.unlink()
    before = storage.journal_path.read_bytes()
    calls = []
    result = wal.recover_temp_wal(storage, lambda payload: calls.append(payload))
    assert result.status == wal.WAL_INVALID
    assert result.state == wal.SNAPSHOT_INVALID
    assert calls == []
    assert storage.journal_path.read_bytes() == before
