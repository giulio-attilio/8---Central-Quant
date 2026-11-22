import ast
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import paper_state_storage


def _load_atomic_writer(source_path):
    source = Path(source_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    wanted = {
        "_trpsf_v1_fsync_directory",
        "_trpsf_v1_atomic_write_json",
    }
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in functions} == wanted
    namespace = {"Path": Path, "json": json, "os": os}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace


def _load_unpatched_trade_registry():
    source_path = Path(__file__).parents[1] / "trade_registry.py"
    module_name = f"_trade_registry_durability_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_registry_directory_sync_delegates_to_guarded_storage(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    calls = []
    namespace["_fsync_guarded_paper_directory"] = lambda path: calls.append(Path(path))
    namespace["_trpsf_v1_fsync_directory"](tmp_path)

    assert calls == [tmp_path]


def test_registry_atomic_write_delegates_to_guarded_same_device_writer(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    calls = []
    target = tmp_path / "trade_registry.json"
    payload = {"open_trades": {"x": 1}}

    def guarded_write(path, value):
        calls.append((Path(path), value))

    namespace["_write_central_paper_audit_json"] = guarded_write

    assert namespace["_trpsf_v1_atomic_write_json"](target, payload)

    assert calls == [(target, payload)]


def test_registry_atomic_writer_propagates_guard_failure(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    target = tmp_path / "trade_registry.json"

    def fail_guarded_write(_path, _payload):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")

    namespace["_write_central_paper_audit_json"] = fail_guarded_write
    with pytest.raises(OSError, match="PAPER_DATA_MOUNT_NOT_VERIFIED"):
        namespace["_trpsf_v1_atomic_write_json"](target, {"open_trades": {"x": 1}})


def test_registry_atomic_writer_preserves_default_string_serialization(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    target = tmp_path / "trade_registry.json"
    calls = []
    namespace["_write_central_paper_audit_json"] = lambda path, payload: calls.append(
        (Path(path), payload)
    )

    assert namespace["_trpsf_v1_atomic_write_json"](
        target, {"metadata": {"path": Path("/tmp/example")}}
    )
    assert calls == [(target, {"metadata": {"path": str(Path("/tmp/example"))}})]


def test_runtime_save_registry_syncs_file_replaces_then_syncs_parent(tmp_path, monkeypatch):
    trade_registry = _load_unpatched_trade_registry()
    target = tmp_path / "trade_registry.json"
    events = []
    real_fsync = os.fsync
    real_replace = os.replace

    def record_fsync(fd):
        events.append("file_fsync")
        return real_fsync(fd)

    def record_replace(source, destination):
        events.append("replace")
        return real_replace(source, destination)

    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(target))
    monkeypatch.setattr(trade_registry.os, "fsync", record_fsync)
    monkeypatch.setattr(trade_registry.os, "replace", record_replace)
    monkeypatch.setattr(
        paper_state_storage,
        "_fsync_directory",
        lambda _path: events.append("directory_fsync"),
    )

    assert trade_registry.save_registry({"open_trades": {"synthetic": {"status": "OPEN"}}}) is True

    saved_open_trade = json.loads(target.read_text(encoding="utf-8"))["open_trades"]["synthetic"]
    assert saved_open_trade["status"] == "OPEN"
    assert events == ["file_fsync", "replace", "directory_fsync"]
    assert not Path(str(target) + ".tmp").exists()


def test_runtime_save_registry_file_fsync_failure_preserves_previous_file(tmp_path, monkeypatch):
    trade_registry = _load_unpatched_trade_registry()
    target = tmp_path / "trade_registry.json"
    original = {"open_trades": {"old": {"status": "OPEN"}}}
    target.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(target))

    def fail_fsync(_fd):
        raise OSError("injected Registry file fsync failure")

    monkeypatch.setattr(trade_registry.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="PERSISTENT_TRADE_REGISTRY_WRITE_FAILED"):
        trade_registry.save_registry({"open_trades": {"new": {"status": "OPEN"}}})

    assert json.loads(target.read_text(encoding="utf-8")) == original
    assert not Path(str(target) + ".tmp").exists()


def test_runtime_save_registry_parent_fsync_failure_raises_after_atomic_replace(tmp_path, monkeypatch):
    trade_registry = _load_unpatched_trade_registry()
    target = tmp_path / "trade_registry.json"
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(target))

    def fail_parent_fsync(_path):
        raise OSError("injected Registry parent directory fsync failure")

    monkeypatch.setattr(paper_state_storage, "_fsync_directory", fail_parent_fsync)
    with pytest.raises(OSError, match="PERSISTENT_TRADE_REGISTRY_WRITE_FAILED"):
        trade_registry.save_registry({"open_trades": {"new": {"status": "OPEN"}}})

    # Rename completed, but durability was not confirmed; the caller sees failure.
    saved_open_trade = json.loads(target.read_text(encoding="utf-8"))["open_trades"]["new"]
    assert saved_open_trade["status"] == "OPEN"


def test_registry_base_loaders_and_writer_use_guarded_storage():
    source_path = Path(__file__).parents[1] / "trade_registry.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    functions = {
        node.name: ast.unparse(node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    for name in ("_ensure_data_dir", "load_registry", "load_registry_read_only", "load_registry_raw_read_only", "save_registry"):
        source = functions[name]
        assert ".mkdir(" not in source
        assert ".exists(" not in source
        assert ".read_text(" not in source
        assert "open(" not in source
    assert "_ensure_persistent_data_dir" in functions["_ensure_data_dir"]
    assert "_paper_file_exists" in functions["load_registry"]
    assert "_read_paper_text" in functions["load_registry"]
    assert "_paper_file_exists" in functions["load_registry_read_only"]
    assert "_read_paper_text" in functions["load_registry_read_only"]
    assert "_paper_file_exists" in functions["load_registry_raw_read_only"]
    assert "_read_paper_text" in functions["load_registry_raw_read_only"]
    assert "_write_json_atomically" in functions["save_registry"]


def test_runtime_registry_parent_sync_fsyncs_and_closes_directory_fd(tmp_path):
    source_path = Path(__file__).parents[1] / "trade_registry.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_fsync_registry_parent"
    )
    namespace = {"Path": Path, "os": os}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
    events = []

    class PosixOsProxy:
        name = "posix"
        O_RDONLY = 1
        O_DIRECTORY = 0x10000

        @staticmethod
        def open(path, flags):
            events.append(("open", str(path), flags))
            return 41

        @staticmethod
        def fsync(fd):
            events.append(("fsync", fd))

        @staticmethod
        def close(fd):
            events.append(("close", fd))

    namespace["os"] = PosixOsProxy
    namespace["_fsync_registry_parent"](tmp_path / "trade_registry.json")

    assert events == [
        ("open", str(tmp_path), PosixOsProxy.O_RDONLY | PosixOsProxy.O_DIRECTORY),
        ("fsync", 41),
        ("close", 41),
    ]


def test_persistent_registry_path_detection_covers_only_data_mount():
    trade_registry = _load_unpatched_trade_registry()
    assert trade_registry._is_persistent_registry_path("/data/trade_registry.json")
    assert trade_registry._is_persistent_registry_path("/data/nested/trade_registry.json")
    assert not trade_registry._is_persistent_registry_path("/data-backup/trade_registry.json")
    assert not trade_registry._is_persistent_registry_path("local/data/trade_registry.json")


def test_missing_persistent_registry_fails_closed_without_creating_file(tmp_path, monkeypatch):
    trade_registry = _load_unpatched_trade_registry()
    target = tmp_path / "trade_registry.json"
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(target))
    monkeypatch.setattr(trade_registry, "_is_persistent_registry_path", lambda _path: True)
    monkeypatch.setattr(
        trade_registry,
        "_ensure_data_dir",
        lambda: pytest.fail("must not create a missing persistent Registry directory"),
    )

    with pytest.raises(FileNotFoundError, match="PERSISTENT_TRADE_REGISTRY_MISSING_FAIL_CLOSED"):
        trade_registry.load_registry()

    assert not target.exists()


@pytest.mark.parametrize("loader_name", ["load_registry_read_only", "load_registry_raw_read_only"])
def test_read_only_registry_loaders_fail_closed_for_missing_persistent_file(
    tmp_path, monkeypatch, loader_name
):
    trade_registry = _load_unpatched_trade_registry()
    target = tmp_path / "trade_registry.json"
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(target))
    monkeypatch.setattr(trade_registry, "_is_persistent_registry_path", lambda _path: True)
    monkeypatch.setattr(
        trade_registry,
        "_ensure_data_dir",
        lambda: pytest.fail("read-only loader must not initialize storage"),
    )

    with pytest.raises(FileNotFoundError, match="PERSISTENT_TRADE_REGISTRY_MISSING_FAIL_CLOSED"):
        getattr(trade_registry, loader_name)()

    assert not target.exists()
