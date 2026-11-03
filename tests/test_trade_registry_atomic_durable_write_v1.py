import ast
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


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


def test_registry_directory_sync_opens_fsyncs_and_closes_parent_directory(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    events = []

    class OsProxy:
        O_RDONLY = 1
        O_DIRECTORY = 0x10000

        @staticmethod
        def open(path, flags):
            events.append(("open", str(path), flags))
            return 37

        @staticmethod
        def fsync(fd):
            events.append(("fsync", fd))

        @staticmethod
        def close(fd):
            events.append(("close", fd))

    namespace["os"] = OsProxy
    namespace["_trpsf_v1_fsync_directory"](tmp_path)

    assert events == [
        ("open", str(tmp_path), OsProxy.O_RDONLY | OsProxy.O_DIRECTORY),
        ("fsync", 37),
        ("close", 37),
    ]


def test_registry_atomic_write_syncs_file_then_replaces_then_syncs_directory(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    events = []
    real_os = os

    class OsProxy:
        O_RDONLY = real_os.O_RDONLY
        O_WRONLY = real_os.O_WRONLY
        O_CREAT = real_os.O_CREAT
        O_TRUNC = real_os.O_TRUNC
        O_DIRECTORY = getattr(real_os, "O_DIRECTORY", 0)

        @staticmethod
        def open(*args, **kwargs):
            return real_os.open(*args, **kwargs)

        @staticmethod
        def fdopen(*args, **kwargs):
            return real_os.fdopen(*args, **kwargs)

        @staticmethod
        def fsync(fd):
            events.append("file_fsync")
            return real_os.fsync(fd)

        @staticmethod
        def replace(source, target):
            events.append("replace")
            return real_os.replace(source, target)

        @staticmethod
        def close(fd):
            return real_os.close(fd)

    namespace["os"] = OsProxy
    namespace["_trpsf_v1_fsync_directory"] = lambda _path: events.append("directory_fsync")
    target = tmp_path / "trade_registry.json"

    assert namespace["_trpsf_v1_atomic_write_json"](target, {"open_trades": {"x": 1}})

    assert json.loads(target.read_text(encoding="utf-8")) == {"open_trades": {"x": 1}}
    assert events == ["file_fsync", "replace", "directory_fsync"]
    assert not target.with_suffix(".json.tmp").exists()


def test_registry_atomic_write_file_fsync_failure_preserves_previous_registry(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    real_os = os

    class OsProxy:
        O_RDONLY = real_os.O_RDONLY
        O_WRONLY = real_os.O_WRONLY
        O_CREAT = real_os.O_CREAT
        O_TRUNC = real_os.O_TRUNC
        O_DIRECTORY = getattr(real_os, "O_DIRECTORY", 0)
        open = staticmethod(real_os.open)
        fdopen = staticmethod(real_os.fdopen)
        replace = staticmethod(real_os.replace)
        close = staticmethod(real_os.close)

        @staticmethod
        def fsync(_fd):
            raise OSError("injected file fsync failure")

    namespace["os"] = OsProxy
    target = tmp_path / "trade_registry.json"
    original = {"open_trades": {"old": 1}}
    target.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(OSError, match="injected file fsync failure"):
        namespace["_trpsf_v1_atomic_write_json"](target, {"open_trades": {"new": 1}})

    assert json.loads(target.read_text(encoding="utf-8")) == original
    assert not target.with_suffix(".json.tmp").exists()


def test_registry_atomic_write_directory_fsync_failure_is_not_reported_as_success(tmp_path):
    namespace = _load_atomic_writer(Path(__file__).parents[1] / "main.py")
    namespace["_trpsf_v1_fsync_directory"] = lambda _path: (_ for _ in ()).throw(
        OSError("injected directory fsync failure")
    )
    target = tmp_path / "trade_registry.json"

    with pytest.raises(OSError, match="injected directory fsync failure"):
        namespace["_trpsf_v1_atomic_write_json"](target, {"open_trades": {"new": 1}})

    # Replacement happened, but durability is unconfirmed; caller must fail closed.
    assert json.loads(target.read_text(encoding="utf-8")) == {"open_trades": {"new": 1}}


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
        trade_registry,
        "_fsync_registry_parent",
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
    with pytest.raises(OSError, match="injected Registry file fsync failure"):
        trade_registry.save_registry({"open_trades": {"new": {"status": "OPEN"}}})

    assert json.loads(target.read_text(encoding="utf-8")) == original
    assert not Path(str(target) + ".tmp").exists()


def test_runtime_save_registry_parent_fsync_failure_raises_after_atomic_replace(tmp_path, monkeypatch):
    trade_registry = _load_unpatched_trade_registry()
    target = tmp_path / "trade_registry.json"
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(target))

    def fail_parent_fsync(_path):
        raise OSError("injected Registry parent directory fsync failure")

    monkeypatch.setattr(trade_registry, "_fsync_registry_parent", fail_parent_fsync)
    with pytest.raises(OSError, match="injected Registry parent directory fsync failure"):
        trade_registry.save_registry({"open_trades": {"new": {"status": "OPEN"}}})

    # Rename completed, but durability was not confirmed; the caller sees failure.
    saved_open_trade = json.loads(target.read_text(encoding="utf-8"))["open_trades"]["new"]
    assert saved_open_trade["status"] == "OPEN"


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
