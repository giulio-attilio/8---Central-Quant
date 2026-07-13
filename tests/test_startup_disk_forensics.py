from __future__ import annotations

import ast
import builtins
import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def module():
    sys.modules.pop("startup_disk_forensics", None)
    return importlib.import_module("startup_disk_forensics")


def _scan(module, root, **environment):
    env = {
        "CENTRAL_STARTUP_DISK_FORENSICS_MAX_FILES": "30",
        "CENTRAL_STARTUP_DISK_FORENSICS_MAX_DIRS": "20",
        "CENTRAL_STARTUP_DISK_FORENSICS_MAX_SCAN_FILES": "100000",
    }
    env.update(environment)
    return module.run_startup_disk_forensics(
        root, root / "data", environ=env, additional_roots=()
    )


def _main_function(name):
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _compile_function(node, namespace):
    node.decorator_list = []
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<isolated-disk-forensics-route>", "exec"), namespace)
    return namespace[node.name]


def test_flag_defaults_true(module):
    assert module.disk_forensics_config({})["enabled"] is True


@pytest.mark.parametrize("value", ["0", "false", "no", "não", "nao", "off", " OFF "])
def test_false_values_disable(module, value):
    assert module.disk_forensics_config(
        {"CENTRAL_STARTUP_DISK_FORENSICS_ENABLED": value}
    )["enabled"] is False


def test_limits_are_clamped(module):
    low = module.disk_forensics_config(
        {
            "CENTRAL_STARTUP_DISK_FORENSICS_MAX_FILES": "0",
            "CENTRAL_STARTUP_DISK_FORENSICS_MAX_DIRS": "0",
            "CENTRAL_STARTUP_DISK_FORENSICS_MAX_SCAN_FILES": "0",
        }
    )
    high = module.disk_forensics_config(
        {
            "CENTRAL_STARTUP_DISK_FORENSICS_MAX_FILES": "999",
            "CENTRAL_STARTUP_DISK_FORENSICS_MAX_DIRS": "999",
        }
    )
    assert (low["max_files"], low["max_dirs"], low["max_scan_files"]) == (1, 1, 1)
    assert (high["max_files"], high["max_dirs"]) == (100, 50)


def test_module_imports_only_standard_library(module):
    source = (ROOT / "startup_disk_forensics.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            imported.add(node.module.split(".")[0])
    assert imported <= {"heapq", "json", "os", "shutil", "datetime", "pathlib"}
    assert imported.isdisjoint(
        {
            "flask",
            "requests",
            "redis",
            "broker",
            "trade_registry",
            "trade_lifecycle_manager",
            "trade_lifecycle_shadow_runtime_adapter",
            "pandas",
            "numpy",
            "ccxt",
            "threading",
            "socket",
        }
    )


def test_module_contains_no_mutating_filesystem_calls():
    source = (ROOT / "startup_disk_forensics.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_attributes = {
        "remove",
        "unlink",
        "rmtree",
        "truncate",
        "rename",
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in banned_attributes
            if node.func.attr == "replace" and isinstance(node.func.value, ast.Name):
                assert node.func.value.id != "os"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open"
    assert '"w"' not in source
    assert '"a"' not in source


def test_disabled_scan_touches_no_disk(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: pytest.fail("disk usage"))
    monkeypatch.setattr(module.os, "scandir", lambda path: pytest.fail("scandir"))
    result = module.run_startup_disk_forensics(
        tmp_path,
        tmp_path / "data",
        environ={"CENTRAL_STARTUP_DISK_FORENSICS_ENABLED": "false"},
    )
    assert result["enabled"] is False
    assert result["scan"]["files_examined"] == 0


def test_disk_usage_and_contract(module, tmp_path):
    (tmp_path / "data").mkdir()
    result = _scan(module, tmp_path)
    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["filesystems"]
    filesystem = result["filesystems"][0]
    assert filesystem["total_bytes"] >= filesystem["used_bytes"]
    assert filesystem["free_bytes"] >= 0
    assert 0 <= filesystem["usage_pct"] <= 100
    assert result["authorities"] == {
        "write_access": False,
        "delete_access": False,
        "registry_write_access": False,
        "lifecycle_write_access": False,
        "broker_access": False,
        "execution_control": False,
    }


def test_largest_files_are_bounded_and_sorted(module, tmp_path):
    (tmp_path / "small.bin").write_bytes(b"x" * 10)
    (tmp_path / "large.log").write_bytes(b"x" * 1000)
    result = _scan(
        module,
        tmp_path,
        CENTRAL_STARTUP_DISK_FORENSICS_MAX_FILES="1",
    )
    assert len(result["largest_files"]) == 1
    assert result["largest_files"][0]["relative_path"] == "large.log"
    assert result["largest_files"][0]["size_bytes"] == 1000
    assert result["largest_files"][0]["classification_hint"] == "LOG"


def test_largest_directories_are_accumulated_and_bounded(module, tmp_path):
    directory = tmp_path / "data" / "nested"
    directory.mkdir(parents=True)
    (directory / "one.bin").write_bytes(b"1" * 100)
    (directory / "two.bin").write_bytes(b"2" * 200)
    result = _scan(
        module,
        tmp_path,
        CENTRAL_STARTUP_DISK_FORENSICS_MAX_DIRS="3",
    )
    assert len(result["largest_directories"]) <= 3
    root_record = next(
        item for item in result["largest_directories"] if item["relative_path"] == "."
    )
    assert root_record["size_bytes"] == 300
    assert root_record["file_count"] == 2


def test_recent_files_use_metadata_only(module, tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    result = _scan(module, tmp_path)
    assert result["recent_files"][0]["relative_path"] == "new.json"
    assert len(result["recent_files"]) <= 20


def test_critical_existing_and_missing_files(module, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    registry = data / "trade_registry.json"
    registry.write_text('{"secret":"not-read"}', encoding="utf-8")
    result = _scan(module, tmp_path)
    existing = next(
        item
        for item in result["critical_files"]
        if item["relative_path"] == "trade_registry.json"
    )
    missing = next(
        item
        for item in result["critical_files"]
        if item["relative_path"] == "trade_journal.jsonl"
    )
    assert existing["exists"] is True
    assert existing["regular_file"] is True
    assert existing["size_bytes"] == registry.stat().st_size
    assert missing["exists"] is False
    assert "secret" not in json.dumps(result)


def test_critical_unreadable_file_is_reported_without_reading(module, tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    registry = data / "trade_registry.json"
    registry.write_text("content", encoding="utf-8")
    original_access = module.os.access
    monkeypatch.setattr(
        module.os,
        "access",
        lambda path, mode: False if Path(path) == registry else original_access(path, mode),
    )
    result = _scan(module, tmp_path)
    record = next(
        item
        for item in result["critical_files"]
        if item["relative_path"] == "trade_registry.json"
    )
    assert record["readable"] is False


def test_symlink_is_never_followed(module, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "hidden.bin").write_bytes(b"x" * 500)
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink unavailable on this platform")
    result = _scan(module, tmp_path)
    assert result["scan"]["symlinks_skipped"] >= 1
    assert not any(
        item["relative_path"].startswith("linked/")
        for item in result["largest_files"]
    )


def test_persistent_iterator_error_finalizes_partial_frame(module, tmp_path, monkeypatch):
    file_path = tmp_path / "seen.log"
    file_path.write_text("seen", encoding="utf-8")
    original_scandir = module.os.scandir
    original_iterator = original_scandir(tmp_path)
    entry = next(original_iterator)
    original_iterator.close()

    class PersistentErrorIterator:
        def __init__(self):
            self.calls = 0
            self.closed = False

        def __next__(self):
            self.calls += 1
            if self.calls == 1:
                return entry
            raise OSError("persistent iterator failure")

        def close(self):
            self.closed = True

    failing_iterator = PersistentErrorIterator()
    monkeypatch.setattr(module.os, "scandir", lambda path: failing_iterator)
    result = module._base_result(True, 100)
    module._scan_roots(
        [{"label": "root", "path": tmp_path}], result, 10, 10, 100
    )

    assert failing_iterator.calls == 2
    assert failing_iterator.closed is True
    assert result["scan"]["errors_count"] == 1
    assert result["scan"]["files_examined"] == 1
    assert result["partial"] is True
    assert result["largest_directories"][0]["partial"] is True
    assert result["largest_directories"][0]["file_count"] == 1


def _root(label, path):
    return {"label": label, "path": path}


def test_select_scan_roots_parent_before_child(module, tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    selected = module._select_scan_roots(
        [_root("parent", parent), _root("child", child)]
    )
    assert [item["label"] for item in selected] == ["parent"]


def test_select_scan_roots_child_before_parent(module, tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    selected = module._select_scan_roots(
        [_root("child", child), _root("parent", parent)]
    )
    assert [item["label"] for item in selected] == ["parent"]


def test_select_scan_roots_preserves_siblings_and_distinct_trees(module, tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    other = tmp_path / "other" / "tree"
    for path in (left, right, other):
        path.mkdir(parents=True)
    selected = module._select_scan_roots(
        [_root("left", left), _root("right", right), _root("other", other)]
    )
    assert [item["label"] for item in selected] == ["left", "right", "other"]


def test_select_scan_roots_deduplicates_identical_paths(module, tmp_path):
    selected = module._select_scan_roots(
        [_root("first", tmp_path), _root("second", tmp_path)]
    )
    assert [item["label"] for item in selected] == ["first"]


@pytest.mark.parametrize("child_first", [False, True])
def test_nested_root_is_not_scanned_twice(module, tmp_path, child_first):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (child / "only.log").write_text("x", encoding="utf-8")
    roots = [_root("parent", parent), _root("child", child)]
    if child_first:
        roots.reverse()
    result = module._base_result(True, 100)
    module._scan_roots(roots, result, 10, 10, 100)
    assert result["scan"]["files_examined"] == 1
    assert result["scan"]["scanned_roots"] == ["parent"]


def test_max_scan_files_is_global_across_distinct_roots(module, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "a.log").write_text("a", encoding="utf-8")
    (second / "b.log").write_text("b", encoding="utf-8")
    (second / "c.log").write_text("c", encoding="utf-8")
    result = module._base_result(True, 2)
    module._scan_roots(
        [_root("first", first), _root("second", second)], result, 10, 10, 2
    )
    assert result["scan"]["scanned_roots"] == ["first", "second"]
    assert result["scan"]["files_examined"] == 2
    assert result["partial"] is True


def test_missing_root_is_safe_and_sanitized(module, tmp_path):
    missing = tmp_path / "does-not-exist"
    result = module.run_startup_disk_forensics(
        missing, environ={}, additional_roots=()
    )
    assert result["ok"] is True
    assert result["scan"]["files_examined"] == 0
    assert result["errors"]
    assert str(missing) not in json.dumps(result)


def test_roots_are_deduplicated(module, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    result = module.run_startup_disk_forensics(
        tmp_path, data, environ={}, additional_roots=()
    )
    roots = result["scan"]["roots"]
    assert len(roots) == len(set(roots))
    assert roots.count("project_data") == 1
    assert "central_data" not in roots


def test_public_paths_are_relative_and_cannot_traverse(module, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "file.log").write_text("x", encoding="utf-8")
    result = _scan(module, tmp_path)
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    for collection in (
        "largest_files",
        "largest_directories",
        "recent_files",
        "critical_files",
    ):
        for item in result[collection]:
            path = item.get("relative_path")
            assert path is None or not path.startswith("/")
            assert path is None or ".." not in Path(path).parts


def test_scan_limit_sets_partial_without_unbounded_collection(module, tmp_path):
    for number in range(5):
        (tmp_path / f"{number}.log").write_text(str(number), encoding="utf-8")
    result = _scan(
        module,
        tmp_path,
        CENTRAL_STARTUP_DISK_FORENSICS_MAX_SCAN_FILES="2",
    )
    assert result["partial"] is True
    assert result["scan"]["files_examined"] == 2
    assert len(result["largest_files"]) <= 2


def test_errors_are_capped_and_sanitized(module, tmp_path, monkeypatch):
    for number in range(120):
        (tmp_path / f"dir-{number}").mkdir()
    original_scandir = module.os.scandir

    def selective_scandir(path):
        if Path(path) == tmp_path:
            return original_scandir(path)
        raise PermissionError(f"blocked absolute path {path}\nsecret-like-line")

    monkeypatch.setattr(module.os, "scandir", selective_scandir)
    result = _scan(module, tmp_path)
    assert result["scan"]["errors_count"] >= 100
    assert len(result["errors"]) == 100
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    assert all(len(item["error"]) <= 300 for item in result["errors"])
    assert "\n" not in "".join(item["error"] for item in result["errors"])


def test_result_is_serializable_and_below_response_limit(module, tmp_path):
    for number in range(40):
        (tmp_path / f"file-{number}.log").write_bytes(b"x" * number)
    result = _scan(module, tmp_path)
    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= 512 * 1024


@pytest.mark.parametrize(
    "collection",
    [
        "errors",
        "critical_files",
        "recent_files",
        "largest_directories",
        "largest_files",
    ],
)
def test_trim_reduces_every_bounded_collection(module, collection, monkeypatch):
    monkeypatch.setattr(module, "_MAX_RESPONSE_BYTES", 2048)
    result = module._base_result(True, 100)
    result[collection] = [{"payload": "x" * 4096}]
    trimmed = module._trim_result(result)
    assert trimmed[collection] == []
    assert trimmed["partial"] is True
    assert len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8")) <= 2048


def test_trim_falls_back_to_minimum_contract_and_preserves_authorities(module):
    result = module._base_result(True, 100)
    result["filesystems"] = [
        {
            "root": "project",
            "total_bytes": 100,
            "used_bytes": 90,
            "free_bytes": 10,
            "usage_pct": 90.0,
        }
    ]
    result["unbounded_unknown_field"] = "x" * (module._MAX_RESPONSE_BYTES + 1024)
    expected_authorities = result["authorities"].copy()
    trimmed = module._trim_result(result)
    encoded = json.dumps(trimmed, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= module._MAX_RESPONSE_BYTES
    assert trimmed["partial"] is True
    assert trimmed["authorities"] == expected_authorities
    assert trimmed["filesystems"] == result["filesystems"]
    assert "unbounded_unknown_field" not in trimmed


def test_result_contains_only_native_json_types(module, tmp_path):
    (tmp_path / "native.log").write_text("x", encoding="utf-8")
    result = _scan(module, tmp_path)

    def assert_native(value):
        assert isinstance(value, (dict, list, str, int, float, bool, type(None)))
        if isinstance(value, dict):
            assert all(isinstance(key, str) for key in value)
            for nested in value.values():
                assert_native(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_native(nested)

    assert_native(result)
    json.dumps(result, ensure_ascii=False)


def test_scanner_never_reads_file_contents(module, tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "trade_registry.json").write_text(
        "content-must-not-be-read", encoding="utf-8"
    )
    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: pytest.fail("file content opened"),
    )
    result = _scan(module, tmp_path)
    assert result["ok"] is True


def test_module_has_no_network_redis_broker_or_threads(module):
    tree = ast.parse((ROOT / "startup_disk_forensics.py").read_text(encoding="utf-8"))
    imported = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported.isdisjoint(
        {"requests", "socket", "urllib", "redis", "broker", "threading", "subprocess"}
    )
    assert calls.isdisjoint(
        {"Thread", "start", "Popen", "run", "call", "check_call", "check_output"}
    )


def test_health_projection_uses_only_memory(module, monkeypatch):
    monkeypatch.setattr(module.os, "scandir", lambda path: pytest.fail("filesystem scan"))
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: pytest.fail("disk usage"))
    result = {
        "ok": True,
        "enabled": True,
        "partial": False,
        "filesystems": [{"usage_pct": 98.5, "free_bytes": 1048576}],
        "largest_files": [{"relative_path": "data/big.jsonl", "size_mb": 42.0}],
    }
    assert module.build_disk_forensics_health(result) == {
        "disk_forensics_available": True,
        "disk_forensics_usage_pct": 98.5,
        "disk_forensics_free_mb": 1.0,
        "disk_forensics_partial": False,
        "disk_forensics_largest_file": "data/big.jsonl",
        "disk_forensics_largest_file_mb": 42.0,
    }


def test_health_disabled_remains_unavailable_and_filesystem_free(module, monkeypatch):
    monkeypatch.setattr(module.os, "scandir", lambda path: pytest.fail("filesystem scan"))
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: pytest.fail("disk usage"))
    health = module.build_disk_forensics_health(
        {"ok": True, "enabled": False, "filesystems": []}
    )
    assert health["disk_forensics_available"] is False
    assert health["disk_forensics_usage_pct"] is None


@pytest.mark.parametrize(
    "absolute_path",
    ["/opt/render/project/src/data/secret.log", "C:/private/secret.log", "../secret.log"],
)
def test_startup_summary_never_exposes_absolute_or_traversal_path(
    module, absolute_path
):
    result = {
        "ok": True,
        "enabled": True,
        "partial": False,
        "filesystems": [{"usage_pct": 90.0, "free_bytes": 1024}],
        "largest_files": [{"relative_path": absolute_path, "size_mb": 1.0}],
    }
    summary = module.build_startup_summary(result)
    assert absolute_path not in summary
    assert "largest_file=None" in summary


def test_startup_scan_is_one_shot_and_precedes_runtime_append():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert source.count("run_startup_disk_forensics(") == 1
    assert source.index("STARTUP_DISK_FORENSICS_RESULT = run_startup_disk_forensics(") < source.index(
        "CENTRAL_DATA_DIR.mkdir("
    )
    assert source.index("STARTUP_DISK_FORENSICS_RESULT = run_startup_disk_forensics(") < source.index(
        "runtime_stability_v1_record_startup()"
    )


def test_endpoint_returns_only_cached_result_and_rejects_query():
    cached = {
        "ok": True,
        "enabled": True,
        "filesystems": [{"usage_pct": 10.0}],
        "module": "startup_disk_forensics",
        "marker": "cached",
    }
    namespace = {
        "request": SimpleNamespace(args={}),
        "STARTUP_DISK_FORENSICS_RESULT": cached,
    }
    route = _compile_function(_main_function("disk_forensics_route"), namespace)
    assert route() == (cached, 200)
    namespace["request"].args = {"rescan": "1"}
    payload, status = route()
    assert status == 400
    assert payload["error"] == "QUERY_PARAMETERS_NOT_SUPPORTED"


def test_endpoint_unavailable_is_sanitized_503():
    namespace = {
        "request": SimpleNamespace(args={}),
        "STARTUP_DISK_FORENSICS_RESULT": {"ok": False, "error": "private"},
    }
    payload, status = _compile_function(
        _main_function("disk_forensics_route"), namespace
    )()
    assert status == 503
    assert payload["error"] == "STARTUP_DIAGNOSTIC_UNAVAILABLE"
    assert "private" not in json.dumps(payload)


@pytest.mark.parametrize(
    "cached",
    [
        {"ok": True, "enabled": False, "filesystems": [{"usage_pct": 10.0}]},
        {"ok": True, "enabled": True, "filesystems": []},
    ],
)
def test_endpoint_disabled_or_without_filesystem_returns_503(cached):
    namespace = {
        "request": SimpleNamespace(args={}),
        "STARTUP_DISK_FORENSICS_RESULT": cached,
    }
    payload, status = _compile_function(
        _main_function("disk_forensics_route"), namespace
    )()
    assert status == 503
    assert payload == {
        "ok": False,
        "module": "startup_disk_forensics",
        "error": "STARTUP_DIAGNOSTIC_UNAVAILABLE",
    }


def test_endpoint_is_get_only_so_mutating_methods_are_405():
    node = _main_function("disk_forensics_route")
    decorators = [ast.unparse(item) for item in node.decorator_list]
    assert len(decorators) == 2
    assert all("methods=['GET']" in item for item in decorators)
    assert all(method not in "".join(decorators) for method in ("POST", "PUT", "PATCH", "DELETE"))


def test_main_health_uses_cached_projection_without_scan():
    expected = {
        "disk_forensics_available": True,
        "disk_forensics_usage_pct": 90.0,
        "disk_forensics_free_mb": 10.0,
        "disk_forensics_partial": False,
        "disk_forensics_largest_file": "data/a.jsonl",
        "disk_forensics_largest_file_mb": 2.0,
    }
    calls = []
    namespace = {
        "central_watchdog_status": lambda: {"ok": True},
        "central_trade_registry_snapshot": lambda include_trades=False: {},
        "automatic_daily_summaries_health": lambda: {},
        "automatic_learning_refresh_health": lambda **kwargs: {},
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": True,
        "build_disk_forensics_health": lambda result: calls.append(result)
        or expected.copy(),
        "STARTUP_DISK_FORENSICS_RESULT": {"ok": True, "cached": True},
    }
    result = _compile_function(_main_function("health"), namespace)()
    assert calls == [{"ok": True, "cached": True}]
    for key, value in expected.items():
        assert result[key] == value


def test_import_and_scan_failures_are_fail_open_in_main():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    import_start = source.index("try:\n    from startup_disk_forensics import")
    import_end = source.index("try:\n    import fcntl", import_start)
    assert "except Exception" in source[import_start:import_end]
    scan_start = source.index("if STARTUP_DISK_FORENSICS_LOADED")
    scan_end = source.index("CENTRAL_DATA_DIR.mkdir", scan_start)
    assert "except Exception" in source[scan_start:scan_end]
    assert '"ok": False' in source[scan_start:scan_end]
