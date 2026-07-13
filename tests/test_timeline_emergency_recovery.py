from __future__ import annotations

import ast
import importlib
import json
import os
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def recovery(monkeypatch):
    sys.modules.pop("timeline_emergency_recovery", None)
    module = importlib.import_module("timeline_emergency_recovery")
    # Mantém os testes pequenos sem relaxar os limites de produção: apenas a
    # unidade interna MiB é reduzida nesta instância isolada.
    monkeypatch.setattr(module, "MIB", 1024)
    return module


def enabled_env(**updates):
    env = {
        "CENTRAL_TIMELINE_EMERGENCY_RECOVERY_ENABLED": "true",
        "CENTRAL_TIMELINE_EMERGENCY_MIN_USAGE_PCT": "80",
        "CENTRAL_TIMELINE_EMERGENCY_MIN_FILE_MB": "64",
        "CENTRAL_TIMELINE_EMERGENCY_KEEP_TAIL_MB": "8",
        "CENTRAL_TIMELINE_EMERGENCY_BLOCK_MB": "1",
    }
    env.update(updates)
    return env


def disk_usage(usage_pct=96.0, free=4000):
    total = 100_000
    used = int(total * usage_pct / 100.0)
    return SimpleNamespace(total=total, used=used, free=free)


def fixed_disk(usage_pct=96.0, free=4000):
    return lambda path: disk_usage(usage_pct, free)


def make_timeline(data_dir, *, final_newline=True, multibyte=False):
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "timeline.jsonl"
    rows = []
    for number in range(1800):
        marker = "ação-ç-🚀" if multibyte else "event"
        rows.append(
            (f'{{"n":{number},"marker":"{marker}","payload":"' + "x" * 28 + '"}}').encode(
                "utf-8"
            )
        )
    payload = b"\n".join(rows)
    if final_newline:
        payload += b"\n"
    target.write_bytes(payload)
    assert target.stat().st_size >= 64 * 1024
    return target, payload


def run(recovery, data_dir, env=None, disk=None):
    return recovery.run_timeline_emergency_recovery(
        data_dir,
        environ=enabled_env() if env is None else env,
        disk_usage_func=fixed_disk() if disk is None else disk,
    )


def test_flag_absent_is_disabled_without_disk_access(recovery, tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "_validate_timeline_target", lambda *args: pytest.fail("disk"))
    result = recovery.run_timeline_emergency_recovery(tmp_path, environ={})
    assert result["status"] == "DISABLED"
    assert result["enabled"] is False
    assert result["attempted"] is False


@pytest.mark.parametrize("value", ["0", "false", "no", "nao", "não", "off", ""])
def test_false_values_disable(recovery, tmp_path, value):
    result = recovery.run_timeline_emergency_recovery(
        tmp_path,
        environ={"CENTRAL_TIMELINE_EMERGENCY_RECOVERY_ENABLED": value},
    )
    assert result["status"] == "DISABLED"


@pytest.mark.parametrize("value", ["1", "true", "yes", "sim", "on", " TRUE "])
def test_true_values_enable(recovery, value):
    config = recovery.timeline_emergency_recovery_config(
        {"CENTRAL_TIMELINE_EMERGENCY_RECOVERY_ENABLED": value}
    )
    assert config["enabled"] is True


def test_defaults_and_clamps(recovery):
    defaults = recovery.timeline_emergency_recovery_config({})
    assert defaults == {
        "enabled": False,
        "min_usage_pct": 95.0,
        "min_file_mb": 256.0,
        "keep_tail_mb": 32.0,
        "block_mb": 1,
    }
    clamped = recovery.timeline_emergency_recovery_config(
        {
            "CENTRAL_TIMELINE_EMERGENCY_MIN_USAGE_PCT": "1",
            "CENTRAL_TIMELINE_EMERGENCY_MIN_FILE_MB": "99999",
            "CENTRAL_TIMELINE_EMERGENCY_KEEP_TAIL_MB": "1",
            "CENTRAL_TIMELINE_EMERGENCY_BLOCK_MB": "99",
        }
    )
    assert clamped == {
        "enabled": False,
        "min_usage_pct": 80.0,
        "min_file_mb": 4096.0,
        "keep_tail_mb": 8.0,
        "block_mb": 8,
    }


def test_threshold_not_reached_skips_without_mutation(recovery, tmp_path):
    target, original = make_timeline(tmp_path)
    result = run(recovery, tmp_path, disk=fixed_disk(79.0))
    assert result["status"] == "THRESHOLD_NOT_REACHED"
    assert target.read_bytes() == original


def test_file_below_minimum_skips(recovery, tmp_path):
    target = tmp_path / "timeline.jsonl"
    target.write_bytes(b'{"small":true}\n')
    result = run(recovery, tmp_path)
    assert result["status"] == "FILE_BELOW_MINIMUM"
    assert target.read_bytes() == b'{"small":true}\n'


def test_file_missing(recovery, tmp_path):
    result = run(recovery, tmp_path)
    assert result["status"] == "FILE_MISSING"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "target_factory",
    [
        lambda data, root: data / "other.jsonl",
        lambda data, root: root / "outside" / "timeline.jsonl",
        lambda data, root: data / ".." / "outside" / "timeline.jsonl",
    ],
)
def test_wrong_basename_outside_and_traversal_are_rejected(
    recovery, tmp_path, target_factory
):
    data = tmp_path / "data"
    data.mkdir()
    target = target_factory(data, tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    result = recovery._validate_timeline_target(data, target)
    assert result["status"] == "INVALID_TARGET"


def test_root_data_dir_is_rejected(recovery):
    root = Path(Path.cwd().anchor)
    result = recovery._validate_timeline_target(root)
    assert result["status"] == "INVALID_TARGET"


def test_symlink_is_rejected(recovery, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    real = tmp_path / "real.jsonl"
    real.write_bytes(b"original")
    target = data / "timeline.jsonl"
    try:
        target.symlink_to(real)
    except OSError:
        pytest.skip("symlink indisponível")
    result = run(recovery, data)
    assert result["status"] == "SYMLINK_REJECTED"
    assert real.read_bytes() == b"original"


def test_hardlinked_target_is_rejected(recovery, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    protected = tmp_path / "protected.jsonl"
    protected.write_bytes(b"protected")
    target = data / "timeline.jsonl"
    try:
        os.link(protected, target)
    except OSError:
        pytest.skip("hardlink indisponível")
    result = run(recovery, data)
    assert result["status"] == "INVALID_TARGET"
    assert protected.read_bytes() == b"protected"


def test_directory_is_rejected(recovery, tmp_path):
    (tmp_path / "timeline.jsonl").mkdir()
    result = run(recovery, tmp_path)
    assert result["status"] == "NOT_REGULAR_FILE"


def test_non_regular_mode_is_rejected(recovery, tmp_path, monkeypatch):
    target = tmp_path / "timeline.jsonl"
    target.write_bytes(b"x")
    original_lstat = Path.lstat

    def fake_lstat(path):
        value = original_lstat(path)
        if Path(path) == target:
            return SimpleNamespace(st_mode=0o020000, st_size=value.st_size, st_nlink=1)
        return value

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    result = run(recovery, tmp_path)
    assert result["status"] == "NOT_REGULAR_FILE"


def test_keep_tail_not_smaller_skips(recovery, tmp_path):
    target, original = make_timeline(tmp_path)
    env = enabled_env(CENTRAL_TIMELINE_EMERGENCY_KEEP_TAIL_MB="256")
    result = run(recovery, tmp_path, env=env)
    assert result["status"] == "KEEP_TAIL_NOT_SMALLER"
    assert target.read_bytes() == original


def test_recovery_preserves_exact_complete_tail(recovery, tmp_path):
    target, original = make_timeline(tmp_path)
    result = run(recovery, tmp_path)
    preserved = target.read_bytes()
    assert result["status"] == "RECOVERED"
    assert preserved == original[result["source_start_offset"] :]
    assert preserved.startswith(b'{"n":')
    assert len(preserved) <= 8 * recovery.MIB
    assert result["first_partial_line_discarded"] is True
    assert result["last_line_incomplete"] is False


def test_last_line_without_newline_is_preserved(recovery, tmp_path):
    target, original = make_timeline(tmp_path, final_newline=False)
    result = run(recovery, tmp_path)
    assert result["status"] == "RECOVERED"
    assert result["last_line_incomplete"] is True
    assert target.read_bytes().endswith(original.split(b"\n")[-1])


def test_utf8_multibyte_boundary_is_byte_identical(recovery, tmp_path):
    target, original = make_timeline(tmp_path, multibyte=True)
    result = run(recovery, tmp_path)
    preserved = target.read_bytes()
    assert preserved == original[result["source_start_offset"] :]
    preserved.decode("utf-8")
    assert "ação-ç-🚀" in preserved.decode("utf-8")


def test_json_is_not_reinterpreted(recovery, tmp_path):
    target, original = make_timeline(tmp_path)
    result = run(recovery, tmp_path)
    preserved = target.read_bytes()
    assert preserved == original[result["source_start_offset"] :]
    assert b'"payload":"xxxxxxxx' in preserved


def test_no_boundary_skips_without_mutation(recovery, tmp_path):
    target = tmp_path / "timeline.jsonl"
    original = b"x" * (70 * recovery.MIB)
    target.write_bytes(original)
    result = run(recovery, tmp_path)
    assert result["status"] == "NO_COMPLETE_LINE_BOUNDARY"
    assert target.read_bytes() == original


def test_sparse_large_fixture_does_not_allocate_production_size(recovery, tmp_path):
    target = tmp_path / "timeline.jsonl"
    with target.open("wb") as stream:
        stream.seek(65 * recovery.MIB)
        for number in range(300):
            stream.write(f'{{"tail":{number},"v":"xxxxxxxxxxxxxxxx"}}\n'.encode())
    result = run(recovery, tmp_path)
    assert result["status"] == "RECOVERED"
    assert target.stat().st_size <= 8 * recovery.MIB


class FileProxy:
    def __init__(self, stream, *, fail=None, events=None, read_sizes=None):
        self.stream = stream
        self.fail = fail
        self.events = events if events is not None else []
        self.read_sizes = read_sizes if read_sizes is not None else []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stream.close()

    def fileno(self):
        return self.stream.fileno()

    def seek(self, *args):
        if self.fail == "seek":
            raise OSError("private seek failure")
        return self.stream.seek(*args)

    def readinto(self, buffer):
        self.read_sizes.append(len(buffer))
        if self.fail == "readinto":
            raise OSError("private read failure")
        return self.stream.readinto(buffer)

    def write(self, value):
        if self.fail == "write":
            raise OSError("private write failure")
        self.events.append("write")
        return self.stream.write(value)

    def flush(self):
        self.events.append("flush")
        return self.stream.flush()

    def truncate(self, size):
        self.events.append("truncate")
        if self.fail == "truncate":
            raise OSError("private truncate failure")
        return self.stream.truncate(size)


def install_proxy(recovery, monkeypatch, *, fail=None, events=None, read_sizes=None):
    def open_proxy(path):
        return FileProxy(
            open(path, "r+b", buffering=0),
            fail=fail,
            events=events,
            read_sizes=read_sizes,
        )

    monkeypatch.setattr(recovery, "_open_target", open_proxy)


def test_copy_uses_limited_blocks_and_no_full_tail_buffer(recovery, tmp_path, monkeypatch):
    target, _ = make_timeline(tmp_path)
    sizes = []
    install_proxy(recovery, monkeypatch, read_sizes=sizes)
    result = run(recovery, tmp_path)
    assert result["status"] == "RECOVERED"
    assert sizes
    assert max(sizes) <= recovery.MIB
    assert target.stat().st_size < result["before"]["file_size_bytes"]


def test_bytes_freed_and_dynamic_free_space_are_correct(recovery, tmp_path):
    target, _ = make_timeline(tmp_path)
    original_size = target.stat().st_size

    def dynamic_disk(path):
        current = target.stat().st_size
        freed = original_size - current
        return SimpleNamespace(total=1_000_000, used=960_000 - freed, free=40_000 + freed)

    result = run(recovery, tmp_path, disk=dynamic_disk)
    assert result["bytes_freed"] == original_size - target.stat().st_size
    assert result["after"]["filesystem_free_bytes"] - result["before"]["filesystem_free_bytes"] == result["bytes_freed"]


def test_fsync_precedes_and_follows_truncate(recovery, tmp_path, monkeypatch):
    make_timeline(tmp_path)
    events = []
    install_proxy(recovery, monkeypatch, events=events)
    monkeypatch.setattr(recovery.os, "fsync", lambda fd: events.append("fsync"))
    result = run(recovery, tmp_path)
    assert result["status"] == "RECOVERED"
    truncate_index = events.index("truncate")
    assert "fsync" in events[:truncate_index]
    assert "fsync" in events[truncate_index + 1 :]
    assert events.index("write") < truncate_index


@pytest.mark.parametrize("failure", ["seek", "readinto", "write", "truncate"])
def test_io_failures_are_sanitized_and_fail_open(
    recovery, tmp_path, monkeypatch, failure
):
    target, original = make_timeline(tmp_path)
    install_proxy(recovery, monkeypatch, fail=failure)
    result = run(recovery, tmp_path)
    assert result["status"] == "ERROR"
    assert result["ok"] is False
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    assert "private" not in serialized
    if failure in {"seek", "readinto"}:
        assert target.read_bytes() == original
    if failure in {"write", "truncate"}:
        assert "in_place_copy_started_no_local_rollback_guaranteed" in result["warnings"]


def test_failure_before_copy_never_truncates(recovery, tmp_path, monkeypatch):
    target, original = make_timeline(tmp_path)
    events = []
    install_proxy(recovery, monkeypatch, fail="seek", events=events)
    result = run(recovery, tmp_path)
    assert result["status"] == "ERROR"
    assert "truncate" not in events
    assert target.read_bytes() == original


def test_one_shot_does_not_touch_file_twice(recovery, tmp_path):
    target, _ = make_timeline(tmp_path)
    first = run(recovery, tmp_path)
    after_first = target.read_bytes()
    second = run(recovery, tmp_path)
    assert first["status"] == "RECOVERED"
    assert second["status"] == "ALREADY_RUN"
    assert second["previous_status"] == "RECOVERED"
    assert target.read_bytes() == after_first


def test_concurrent_calls_mutate_once(recovery, tmp_path):
    make_timeline(tmp_path)
    results = []

    def invoke():
        results.append(run(recovery, tmp_path))

    workers = [threading.Thread(target=invoke) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sum(item["status"] == "RECOVERED" for item in results) == 1
    assert sum(item["status"] == "ALREADY_RUN" for item in results) == 3


def test_recovery_creates_no_additional_file(recovery, tmp_path):
    make_timeline(tmp_path)
    before = {path.name for path in tmp_path.iterdir()}
    result = run(recovery, tmp_path)
    after = {path.name for path in tmp_path.iterdir()}
    assert result["status"] == "RECOVERED"
    assert before == after == {"timeline.jsonl"}
    assert not any(path.suffix == ".tmp" or "backup" in path.name for path in tmp_path.iterdir())


def test_other_authority_and_jsonl_files_remain_intact(recovery, tmp_path):
    make_timeline(tmp_path)
    names = [
        "trade_registry.json",
        "trade_lifecycle.jsonl",
        "trade_journal.jsonl",
        "history_events.jsonl",
        "decision_log.jsonl",
        "shadow_events.jsonl",
        "central_runtime_events.jsonl",
    ]
    expected = {}
    for number, name in enumerate(names):
        payload = f"protected-{number}".encode()
        (tmp_path / name).write_bytes(payload)
        expected[name] = payload
    result = run(recovery, tmp_path)
    assert result["status"] == "RECOVERED"
    assert {name: (tmp_path / name).read_bytes() for name in names} == expected


def test_module_uses_only_allowed_standard_library_and_no_threads_started():
    source = (ROOT / "timeline_emergency_recovery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert imported <= {"os", "shutil", "threading", "pathlib"}
    assert calls.isdisjoint({"Thread", "start", "requests", "socket", "Redis"})


def test_module_never_uses_full_file_read_or_destructive_path_calls():
    source = (ROOT / "timeline_emergency_recovery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert attributes.isdisjoint(
        {"read", "readlines", "read_text", "splitlines", "unlink", "remove", "rmtree", "rename", "replace"}
    )
    assert "readinto" in attributes


def test_no_network_redis_broker_registry_lifecycle_or_shadow_imports(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network"))
    source = (ROOT / "timeline_emergency_recovery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(
        {
            "requests", "redis", "broker", "trade_registry",
            "trade_lifecycle_manager", "shadow_runtime_adapter", "ccxt",
            "pandas", "numpy",
        }
    )


def test_health_projection_is_memory_only(recovery, monkeypatch):
    monkeypatch.setattr(recovery.shutil, "disk_usage", lambda path: pytest.fail("disk"))
    monkeypatch.setattr(recovery.Path, "lstat", lambda path: pytest.fail("disk"))
    result = {
        "enabled": True,
        "status": "RECOVERED",
        "attempted": True,
        "before": {"file_size_mb": 333.6},
        "after": {"file_size_mb": 31.9},
        "bytes_freed": 301 * recovery.MIB,
        "target_reached": True,
    }
    assert recovery.build_timeline_emergency_recovery_health(result) == {
        "timeline_emergency_recovery_enabled": True,
        "timeline_emergency_recovery_status": "RECOVERED",
        "timeline_emergency_recovery_attempted": True,
        "timeline_emergency_recovery_before_mb": 333.6,
        "timeline_emergency_recovery_after_mb": 31.9,
        "timeline_emergency_recovery_freed_mb": 301.0,
        "timeline_emergency_recovery_target_reached": True,
    }


def test_startup_integration_order_is_strictly_early():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    recovery_call = source.index("TIMELINE_EMERGENCY_RECOVERY_RESULT = run_timeline_emergency_recovery(")
    disk_scan = source.index("STARTUP_DISK_FORENSICS_RESULT = run_startup_disk_forensics(")
    data_mkdir = source.index("CENTRAL_DATA_DIR.mkdir(")
    history_import = source.index("import history_manager as _canonical_timeline_history_manager")
    runtime_append = source.index("runtime_stability_v1_record_startup()")
    assert source.index("CENTRAL_DATA_DIR = _resolve_central_data_dir()") < recovery_call
    assert recovery_call < disk_scan < data_mkdir < history_import < runtime_append
    assert recovery_call < source.index("from automatic_daily_summaries import")
    assert recovery_call < source.index("import event_bus as central_event_bus")
    assert recovery_call < source.index("import trade_registry as central_trade_registry")
    assert source.count("run_timeline_emergency_recovery(") == 1


def test_main_has_no_mutating_recovery_endpoint():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "timeline_emergency_recovery_route" not in source
    assert "rescan_timeline" not in source


def test_result_is_json_serializable_and_paths_are_sanitized(recovery, tmp_path):
    make_timeline(tmp_path)
    result = run(recovery, tmp_path)
    serialized = json.dumps(result, ensure_ascii=False)
    assert result["target"] == "timeline.jsonl"
    assert str(tmp_path) not in serialized
    assert ".." not in result["target"]


def test_main_health_reads_cached_result_only():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    health = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "health"
    )
    rendered = ast.unparse(health)
    assert "TIMELINE_EMERGENCY_RECOVERY_RESULT" in rendered
    assert "build_timeline_emergency_recovery_health" in rendered
    assert "run_timeline_emergency_recovery" not in rendered
    assert "disk_usage" not in rendered
    assert "open(" not in rendered
