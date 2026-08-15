from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import trade_evidence_identity_offset_index_v1 as index_v1
import trade_evidence_identity_offset_maintenance_v1 as maintenance


ROOT = Path(__file__).resolve().parents[1]
MAIN_TREE = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))


def _forbid_network(*args, **kwargs):
    raise AssertionError("network access attempted during index maintenance test")


@pytest.fixture(autouse=True)
def _safe_process(monkeypatch):
    maintenance.reset_maintenance_telemetry_for_tests()
    monkeypatch.setattr(socket, "create_connection", _forbid_network)
    monkeypatch.setattr(socket, "getaddrinfo", _forbid_network)
    monkeypatch.setattr(socket.socket, "connect", _forbid_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _forbid_network)
    yield
    maintenance.reset_maintenance_telemetry_for_tests()


def _line(number: int) -> bytes:
    return (
        json.dumps(
            {
                "trade_uuid": f"MAINT-{number}",
                "event_id": f"EVENT-{number}",
                "event_type": "POSITION_OPEN",
                "timestamp": f"2026-08-15T12:00:{number % 60:02d}Z",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _build_config():
    return index_v1.BuildConfig(
        block_bytes=32,
        segment_target_bytes=256,
        batch_bytes=2048,
        batch_lines=4,
        max_line_bytes=4096,
        anchor_bytes=16,
        busy_timeout_ms=25,
    )


def _build_ready(tmp_path: Path, source_id: str):
    stem = "history_events" if source_id == "history_manager" else "timeline"
    source = tmp_path / f"{stem}.jsonl"
    index = tmp_path / f"{stem}.identity-offset-v1.sqlite3"
    source.write_bytes(_line(1))
    report = index_v1.build_index(
        source,
        index,
        source_id,
        config=_build_config(),
        measure_memory=False,
    )
    assert report.state == "READY"
    return source, index, report


def _config(
    tmp_path: Path,
    *,
    enabled: bool = True,
    min_lag_bytes: int = 1,
    max_lag_bytes: int = 1024,
    cooldown: float = 0.0,
    history_paths=None,
    timeline_paths=None,
):
    history_source, history_index = history_paths or (
        tmp_path / "history_events.jsonl",
        tmp_path / "history_events.identity-offset-v1.sqlite3",
    )
    timeline_source, timeline_index = timeline_paths or (
        tmp_path / "timeline.jsonl",
        tmp_path / "timeline.identity-offset-v1.sqlite3",
    )
    return maintenance.MaintenanceConfig(
        enabled=enabled,
        interval_seconds=3600.0,
        min_lag_bytes=min_lag_bytes,
        max_lag_bytes=max(max_lag_bytes, min_lag_bytes),
        min_seconds_between_runs=cooldown,
        busy_timeout_seconds=0.05,
        startup_grace_seconds=300.0,
        min_free_bytes=1,
        history_source_path=history_source,
        history_index_path=history_index,
        timeline_source_path=timeline_source,
        timeline_index_path=timeline_index,
        lock_path=tmp_path / ".maintenance.lock",
    )


def _eligible(source_id: str, *, lag: int = 100) -> maintenance.MaintenanceCheck:
    return maintenance.MaintenanceCheck(
        maintenance.CATCH_UP_ELIGIBLE,
        index_v1.INDEX_PARTIAL,
        source_size=1000,
        safe_watermark=1000 - lag,
        lag_bytes=lag,
        generation_uuid="36a70813-563e-4553-b694-251abb833f21",
        state="READY",
    )


def _report(source_id: str, *, partial: bool = False):
    return SimpleNamespace(
        final_validation_status=(
            index_v1.INDEX_PARTIAL
            if partial
            else index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
        ),
        remaining_lag_bytes=7 if partial else 0,
        source_size_after=1007 if partial else 1000,
        source_size_before=1000,
        safe_watermark_before=900,
        safe_watermark_after=1000,
        processed_append_bytes=100,
        duration_seconds=1.25,
        verified_prefix_bytes=900,
        generation_uuid="36a70813-563e-4553-b694-251abb833f21",
    )


class _Lock:
    active = 0

    def __enter__(self):
        assert _Lock.active == 0
        _Lock.active += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        _Lock.active -= 1


def _route_node(name: str):
    return next(
        copy.deepcopy(node)
        for node in MAIN_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _compile_route(name: str):
    node = _route_node(name)
    node.decorator_list = []
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace = {}
    exec(compile(tree, "<isolated-maintenance-status-route>", "exec"), namespace)
    return namespace[name]


def test_config_is_default_off_and_explicit_true_uses_conservative_defaults(tmp_path):
    absent = maintenance.MaintenanceConfig.from_environ({}, data_dir=tmp_path)
    enabled = maintenance.MaintenanceConfig.from_environ(
        {"TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_ENABLED": "true"},
        data_dir=tmp_path,
    )

    assert absent.enabled is False
    assert enabled.enabled is True
    assert enabled.interval_seconds == 3600
    assert enabled.min_lag_bytes == 4 * 1024 * 1024
    assert enabled.max_lag_bytes == 64 * 1024 * 1024
    assert enabled.min_seconds_between_runs == 3600
    assert enabled.busy_timeout_seconds == 0.25
    assert enabled.startup_grace_seconds == 300
    assert enabled.history_index_path == tmp_path / "history_events.identity-offset-v1.sqlite3"


def test_disabled_tick_and_start_do_not_inspect_lock_or_create_thread(tmp_path):
    config = _config(tmp_path, enabled=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled maintenance touched work")

    snapshot = maintenance.run_maintenance_tick(
        config,
        inspect_fn=forbidden,
        catch_up_fn=forbidden,
        disk_usage_fn=forbidden,
        lock_factory=forbidden,
    )
    started = maintenance.start_auto_maintenance(
        config=config,
        thread_factory=forbidden,
    )

    assert started is False
    assert snapshot["last_status"] == maintenance.DISABLED
    assert snapshot["thread_started"] is False
    assert list(tmp_path.iterdir()) == []


def test_bounded_inspection_classifies_zero_small_and_threshold_lag(tmp_path):
    source, index, built = _build_ready(tmp_path, "timeline")
    spec = maintenance.SourceSpec("timeline", source, index)

    zero = maintenance.inspect_maintenance_source(
        spec,
        _config(tmp_path, min_lag_bytes=32),
    )
    with source.open("ab") as handle:
        handle.write(b"x" * 8)
    small = maintenance.inspect_maintenance_source(
        spec,
        _config(tmp_path, min_lag_bytes=32),
    )
    with source.open("ab") as handle:
        handle.write(b"y" * 32)
    eligible = maintenance.inspect_maintenance_source(
        spec,
        _config(tmp_path, min_lag_bytes=32),
    )

    assert zero.status == maintenance.SKIP_SMALL_LAG and zero.lag_bytes == 0
    assert zero.safe_watermark == built.safe_watermark
    assert small.status == maintenance.SKIP_SMALL_LAG and small.lag_bytes == 8
    assert eligible.status == maintenance.CATCH_UP_ELIGIBLE
    assert eligible.lag_bytes == 40


def test_inspection_handles_not_ready_missing_source_change_and_max_lag_alert(tmp_path):
    source, index, _ = _build_ready(tmp_path, "timeline")
    spec = maintenance.SourceSpec("timeline", source, index)
    config = _config(tmp_path, min_lag_bytes=1, max_lag_bytes=4)

    missing = maintenance.inspect_maintenance_source(
        maintenance.SourceSpec("timeline", source, tmp_path / "missing.sqlite3"),
        config,
    )
    with sqlite3.connect(index) as connection:
        connection.execute("UPDATE source_state SET state='REVALIDATING'")
    not_ready = maintenance.inspect_maintenance_source(spec, config)
    with sqlite3.connect(index) as connection:
        connection.execute("UPDATE source_state SET state='READY'")
    original = source.read_bytes()
    source.write_bytes(b"X" + original[1:] + b"append")
    changed = maintenance.inspect_maintenance_source(spec, config)

    assert missing.status == maintenance.INDEX_MISSING
    assert not_ready.status == maintenance.SKIP_NOT_READY
    assert changed.status == maintenance.SOURCE_CHANGED
    assert changed.validation_status == index_v1.INDEX_SOURCE_CHANGED


def test_low_disk_lock_busy_and_cooldown_never_call_catch_up(tmp_path):
    config = _config(tmp_path, cooldown=3600, max_lag_bytes=50)
    calls = []

    def catch_up(*args, **kwargs):
        calls.append(args)
        return _report(args[2])

    def eligible(spec, selected):
        return _eligible(spec.source_id)

    low_disk = maintenance.run_maintenance_tick(
        config,
        now_fn=lambda: time.time() + 10,
        inspect_fn=eligible,
        catch_up_fn=catch_up,
        disk_usage_fn=lambda path: SimpleNamespace(free=0),
        lock_factory=lambda path: _Lock(),
    )
    maintenance.reset_maintenance_telemetry_for_tests()
    lock_busy = maintenance.run_maintenance_tick(
        config,
        now_fn=lambda: time.time() + 20,
        inspect_fn=eligible,
        catch_up_fn=catch_up,
        disk_usage_fn=lambda path: SimpleNamespace(free=10**9),
        lock_factory=lambda path: None,
    )
    future = time.time() + 30
    for spec in config.source_specs():
        stamp = spec.cooldown_stamp_path
        stamp.touch()
        os.utime(stamp, (future, future))
    cooldown = maintenance.run_maintenance_tick(
        config,
        now_fn=lambda: future + 1,
        inspect_fn=eligible,
        catch_up_fn=catch_up,
        disk_usage_fn=lambda path: SimpleNamespace(free=10**9),
        lock_factory=lambda path: _Lock(),
    )

    assert calls == []
    assert low_disk["sources"]["timeline"]["last_status"] == maintenance.LOW_DISK
    assert low_disk["sources"]["timeline"]["lag_above_max"] is True
    assert lock_busy["sources"]["timeline"]["last_status"] == maintenance.LOCK_BUSY
    assert lock_busy["sources"]["timeline"]["lock_busy_count"] == 1
    assert cooldown["sources"]["history_manager"]["last_status"] == maintenance.COOLDOWN


def test_global_lock_is_nonblocking_single_flight(tmp_path):
    path = tmp_path / ".maintenance.lock"
    first = maintenance.acquire_maintenance_file_lock(path)
    assert first is not None
    try:
        assert maintenance.acquire_maintenance_file_lock(path) is None
    finally:
        first.__exit__(None, None, None)
    second = maintenance.acquire_maintenance_file_lock(path)
    assert second is not None
    second.__exit__(None, None, None)


def test_tick_executes_history_then_timeline_serially_and_records_success(tmp_path):
    config = _config(tmp_path)
    inspect_order = []
    catchup_order = []

    def inspect(spec, selected):
        inspect_order.append(spec.source_id)
        return _eligible(spec.source_id)

    def catch_up(source, index, source_id, *, measure_memory):
        assert _Lock.active == 1
        assert measure_memory is False
        catchup_order.append(source_id)
        return _report(source_id)

    snapshot = maintenance.run_maintenance_tick(
        config,
        now_fn=lambda: time.time() + 100,
        inspect_fn=inspect,
        catch_up_fn=catch_up,
        disk_usage_fn=lambda path: SimpleNamespace(free=10**9),
        lock_factory=lambda path: _Lock(),
    )

    assert inspect_order == ["history_manager", "history_manager", "timeline", "timeline"]
    assert catchup_order == ["history_manager", "timeline"]
    assert _Lock.active == 0
    assert snapshot["last_status"] == maintenance.CATCH_UP_OK
    for source in snapshot["sources"].values():
        assert source["last_status"] == maintenance.CATCH_UP_OK
        assert source["run_count"] == source["success_count"] == 1
        assert source["processed_append_bytes"] == 100
        assert source["verified_prefix_bytes"] == 900
        assert len(source["generation_uuid_masked"]) == 12


def test_partial_live_append_and_exception_are_fail_safe_with_retry_cooldown(tmp_path):
    config = _config(tmp_path, cooldown=3600)
    now = time.time() + 200
    calls = []

    def inspect(spec, selected):
        return _eligible(spec.source_id)

    def partial_or_fail(source, index, source_id, *, measure_memory):
        calls.append(source_id)
        if source_id == "history_manager":
            return _report(source_id, partial=True)
        raise RuntimeError("private journal path")

    first = maintenance.run_maintenance_tick(
        config,
        now_fn=lambda: now,
        inspect_fn=inspect,
        catch_up_fn=partial_or_fail,
        disk_usage_fn=lambda path: SimpleNamespace(free=10**9),
        lock_factory=lambda path: _Lock(),
    )
    second = maintenance.run_maintenance_tick(
        config,
        now_fn=lambda: now + 1,
        inspect_fn=inspect,
        catch_up_fn=partial_or_fail,
        disk_usage_fn=lambda path: SimpleNamespace(free=10**9),
        lock_factory=lambda path: _Lock(),
    )

    assert calls == ["history_manager", "timeline"]
    assert first["sources"]["history_manager"]["last_status"] == maintenance.CATCH_UP_PARTIAL
    assert first["sources"]["timeline"]["last_status"] == maintenance.CATCH_UP_FAILED
    assert first["sources"]["timeline"]["last_error_type"] == "RuntimeError"
    assert second["sources"]["history_manager"]["last_status"] == maintenance.COOLDOWN
    assert second["sources"]["timeline"]["last_status"] == maintenance.COOLDOWN


def test_repeated_small_lag_ticks_do_nothing_then_crossing_threshold_runs_once(tmp_path):
    history = _build_ready(tmp_path, "history_manager")[:2]
    timeline = _build_ready(tmp_path, "timeline")[:2]
    config = _config(
        tmp_path,
        min_lag_bytes=128,
        history_paths=history,
        timeline_paths=timeline,
    )
    calls = []

    def catch_up(source, index, source_id, *, measure_memory):
        calls.append(source_id)
        return index_v1.catch_up_index(source, index, source_id, measure_memory=False)

    for source, _index in (history, timeline):
        with source.open("ab") as handle:
            handle.write(b"x" * 32)
    first = maintenance.run_maintenance_tick(config, catch_up_fn=catch_up)
    second = maintenance.run_maintenance_tick(config, catch_up_fn=catch_up)
    with history[0].open("ab") as handle:
        handle.write(_line(2))
    third = maintenance.run_maintenance_tick(config, catch_up_fn=catch_up)

    assert calls == ["history_manager"]
    assert first["sources"]["history_manager"]["skip_small_lag_count"] == 1
    assert second["sources"]["history_manager"]["skip_small_lag_count"] == 2
    assert third["sources"]["history_manager"]["last_status"] == maintenance.CATCH_UP_OK
    assert history[0].read_bytes().endswith(_line(2))


def test_scheduler_waits_for_grace_and_isolates_tick_exception(tmp_path):
    config = _config(tmp_path)
    waits = []
    ticks = []

    class StopEvent:
        def wait(self, seconds):
            waits.append(seconds)
            return len(waits) >= 2

        def is_set(self):
            return False

    def tick(selected):
        ticks.append(selected)
        raise RuntimeError("scheduler fault")

    maintenance.maintenance_loop(config, stop_event=StopEvent(), tick_fn=tick)
    snapshot = maintenance.get_maintenance_telemetry_snapshot()

    assert waits == [300.0, 3600.0]
    assert ticks == [config]
    assert snapshot["last_status"] == maintenance.CATCH_UP_FAILED
    assert snapshot["last_error_type"] == "RuntimeError"


def test_source_inspection_exception_isolated_and_next_source_still_checked(tmp_path):
    config = _config(tmp_path)
    inspected = []

    def inspect(spec, selected):
        inspected.append(spec.source_id)
        if spec.source_id == "history_manager":
            raise RuntimeError("history inspection failed")
        return maintenance.MaintenanceCheck(
            maintenance.SKIP_SMALL_LAG,
            index_v1.INDEX_COMPLETE_FOR_SNAPSHOT,
            state="READY",
        )

    snapshot = maintenance.run_maintenance_tick(
        config,
        inspect_fn=inspect,
        catch_up_fn=lambda *args, **kwargs: pytest.fail("catch-up called"),
    )

    assert inspected == ["history_manager", "timeline"]
    assert snapshot["last_status"] == maintenance.CATCH_UP_FAILED
    assert snapshot["sources"]["history_manager"]["last_error_type"] == "RuntimeError"
    assert snapshot["sources"]["timeline"]["last_status"] == maintenance.SKIP_SMALL_LAG


def test_enabled_scheduler_starts_one_named_daemon_thread_only(tmp_path):
    config = _config(tmp_path)
    created = []

    class FakeThread:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.started = False

        def start(self):
            self.started = True

    assert maintenance.start_auto_maintenance(
        config=config,
        thread_factory=FakeThread,
    ) is True
    assert maintenance.start_auto_maintenance(
        config=config,
        thread_factory=FakeThread,
    ) is False
    assert len(created) == 1
    assert created[0]["daemon"] is True
    assert created[0]["name"] == "trade-evidence-index-auto-maintenance-v1"
    assert created[0]["target"] is maintenance.maintenance_loop
    assert maintenance.get_maintenance_telemetry_snapshot()["thread_started"] is True


def test_status_endpoint_is_get_only_bounded_defensive_and_read_only(monkeypatch, tmp_path):
    node = _route_node("trade_evidence_index_maintenance_status_v1_route")
    decorators = [ast.unparse(item) for item in node.decorator_list]
    assert decorators == [
        "app.route('/tradeevidenceindex/maintenance/status', methods=['GET'])"
    ]
    snapshot = maintenance.get_maintenance_telemetry_snapshot()
    snapshot.update({"secret": "TOKEN", "path": "C:/private/index.sqlite3"})
    snapshot["sources"]["history_manager"].update({
        "generation_uuid": "raw-generation",
        "source_path": "C:/private/history.jsonl",
        "payload": {"token": "TOKEN"},
        "generation_uuid_masked": hashlib.sha256(b"generation").hexdigest()[:12],
    })
    original = copy.deepcopy(snapshot)
    calls = []

    def getter():
        calls.append(True)
        return copy.deepcopy(snapshot)

    monkeypatch.setitem(
        sys.modules,
        "trade_evidence_identity_offset_maintenance_v1",
        SimpleNamespace(get_maintenance_telemetry_snapshot=getter),
    )
    journal = tmp_path / "journal.jsonl"
    journal.write_bytes(b"unchanged")
    before = journal.read_bytes()

    payload, status = _compile_route(
        "trade_evidence_index_maintenance_status_v1_route"
    )()
    payload["maintenance"]["sources"]["history_manager"]["run_count"] = 999
    encoded = json.dumps(payload, sort_keys=True)

    assert status == 200 and calls == [True]
    assert "TOKEN" not in encoded and "C:/private" not in encoded
    assert "raw-generation" not in encoded
    assert snapshot == original
    assert journal.read_bytes() == before


def test_status_endpoint_import_failure_is_sanitized(monkeypatch):
    monkeypatch.setitem(sys.modules, "trade_evidence_identity_offset_maintenance_v1", None)
    payload, status = _compile_route(
        "trade_evidence_index_maintenance_status_v1_route"
    )()

    assert status == 503
    assert payload["ok"] is False
    assert payload["status"] == "UNAVAILABLE"
    assert payload["error_type"] == "ModuleNotFoundError"
    assert set(payload) == {"ok", "module", "status", "error_type"}


def test_request_paths_never_call_maintenance_or_catch_up():
    for name in (
        "trade_timeline_validator_v1_route",
        "live_trade_snapshot_v1_route",
        "trade_evidence_index_shadow_status_v1_route",
        "trade_evidence_index_maintenance_status_v1_route",
    ):
        source = ast.unparse(_route_node(name))
        assert "catch_up_index" not in source
        assert "run_maintenance_tick" not in source
        assert "start_auto_maintenance" not in source
    status_source = ast.unparse(
        _route_node("trade_evidence_index_maintenance_status_v1_route")
    )
    assert "get_maintenance_telemetry_snapshot()" in status_source
    assert "sqlite3" not in status_source
    assert "open(" not in status_source


def test_module_never_builds_rebuilds_or_writes_journals_and_phase_b_stays_separate():
    source = (ROOT / "trade_evidence_identity_offset_maintenance_v1.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported_index_names = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "trade_evidence_identity_offset_index_v1"
        for alias in node.names
    }
    assert "catch_up_index" in imported_index_names
    assert "build_index" not in imported_index_names
    assert "trade_timeline_validator" not in source
    assert "live_trade_snapshot" not in source
    assert "trade_registry" not in source.lower()
    assert "broker" not in source.lower()
    assert "requests" not in source.lower()
    assert 'source.open("rb")' in source
    assert 'source.open("ab")' not in source
    assert 'source.open("wb")' not in source


def test_startup_integration_is_fail_open_and_outside_request_paths():
    startup = ast.unparse(_route_node("start_central_runtime_once"))
    assert "start_auto_maintenance(data_dir=CENTRAL_DATA_DIR)" in startup
    assert "except Exception as exc" in startup
    assert "trade_evidence_identity_offset_maintenance_v1" in startup
