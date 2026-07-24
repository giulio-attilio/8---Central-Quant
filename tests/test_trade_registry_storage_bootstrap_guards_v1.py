from __future__ import annotations

import ast
import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
_FUNCTIONS = None


def _main_function(name):
    global _FUNCTIONS
    if _FUNCTIONS is None:
        tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
        _FUNCTIONS = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
    return _FUNCTIONS[name]


def _compile(names, namespace):
    nodes = []
    for name in names:
        node = copy.deepcopy(_main_function(name))
        node.decorator_list = []
        nodes.append(node)
    tree = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<isolated-trpsf-guards>", "exec"), namespace)
    return namespace


def _patch_namespace(tmp_path, bootstrap):
    original_load = lambda: None
    original_save = lambda payload: True
    registry = SimpleNamespace(
        TRADE_REGISTRY_FILE=tmp_path / "old-registry.json",
        load_registry=original_load,
        save_registry=original_save,
    )

    def patched_load():
        return None

    def patched_save(payload):
        return True

    return {
        "Path": Path,
        "central_trade_registry": registry,
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {
            "patched": False,
            "migration_done": False,
            "active_file": None,
            "original_registry_file": None,
            "legacy_files": [],
            "last_status": None,
            "last_load_ok": None,
            "last_write_ok": None,
            "last_error": None,
            "migrated_from_legacy": False,
        },
        "_TRPSF_V1_ORIGINAL_LOAD_REGISTRY": None,
        "_TRPSF_V1_ORIGINAL_SAVE_REGISTRY": None,
        "_trpsf_v1_active_file": lambda: (
            tmp_path / "must-not-be-created" / "trade_registry.json"
        ),
        "_trpsf_v1_legacy_candidate_paths": lambda: [],
        "_trpsf_v1_patched_load_registry": patched_load,
        "_trpsf_v1_patched_save_registry": patched_save,
        "_trpsf_v1_bootstrap_registry": bootstrap,
        "_trpsf_v1_now": lambda: "fixed",
        "_trpsf_v1_atomic_write_json": lambda *args, **kwargs: pytest.fail(
            "writer reached while only installing the patch"
        ),
        "TRADE_REGISTRY_IMPORT_ERROR": None,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
    }


def test_apply_patch_without_bootstrap_does_not_create_or_write(tmp_path):
    bootstrap_calls = []
    namespace = _patch_namespace(
        tmp_path,
        lambda force=False: bootstrap_calls.append(force)
        or pytest.fail("bootstrap reached"),
    )
    _compile(["_trpsf_v1_apply_patch"], namespace)

    result = namespace["_trpsf_v1_apply_patch"](
        run_bootstrap=False, force=False
    )

    assert result["status"] == "PATCH_INSTALLED_MIGRATION_PENDING"
    assert result["write_required"] is False
    assert result["write_performed"] is False
    assert bootstrap_calls == []
    assert not (tmp_path / "must-not-be-created").exists()
    assert (
        namespace["central_trade_registry"].load_registry
        is namespace["_trpsf_v1_patched_load_registry"]
    )
    assert (
        namespace["central_trade_registry"].save_registry
        is namespace["_trpsf_v1_patched_save_registry"]
    )


def test_explicit_force_path_invokes_bootstrap_exactly_once(tmp_path):
    bootstrap_calls = []

    def bootstrap(force=False):
        bootstrap_calls.append(force)
        return {
            "ok": True,
            "status": "ACTIVE_PERSISTENT",
            "write_performed": False,
        }

    namespace = _patch_namespace(tmp_path, bootstrap)
    _compile(["_trpsf_v1_apply_patch"], namespace)

    result = namespace["_trpsf_v1_apply_patch"](
        run_bootstrap=True, force=True
    )

    assert result["status"] == "ACTIVE_PERSISTENT"
    assert bootstrap_calls == [True]


class _RecordingLock:
    def __init__(self):
        self.depth = 0
        self.enters = 0
        self.exits = 0

    def __enter__(self):
        self.depth += 1
        self.enters += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.depth -= 1
        self.exits += 1
        return False


def test_patched_loader_never_bootstraps_and_normalizes_closed_dict_under_lock(
    tmp_path,
):
    lock = _RecordingLock()
    raw = {
        "open_trades": {},
        "closed_trades": {
            "legacy-index": {
                "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
                "status": "CLOSED",
            }
        },
    }
    reads = []
    normalizations = []

    def read_json(path):
        assert lock.depth == 1
        reads.append(Path(path))
        return copy.deepcopy(raw)

    def normalize(registry):
        assert lock.depth == 1
        normalizations.append(copy.deepcopy(registry))
        normalized = copy.deepcopy(registry)
        normalized["closed_trades"] = list(
            normalized["closed_trades"].values()
        )
        return normalized

    namespace = {
        "Path": Path,
        "central_trade_registry": SimpleNamespace(
            _lock=lock,
            _normalize_registry=normalize,
        ),
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: tmp_path / "trade_registry.json",
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_bootstrap_registry": lambda *args, **kwargs: pytest.fail(
            "loader must never bootstrap"
        ),
    }
    _compile(
        [
            "_trpsf_v1_registry_lock",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )

    result = namespace["_trpsf_v1_patched_load_registry"]()

    assert len(reads) == 1
    assert len(normalizations) == 1
    assert lock.enters == lock.exits == 1
    assert lock.depth == 0
    assert isinstance(result["closed_trades"], list)
    assert result["closed_trades"][0]["status"] == "CLOSED"
    assert namespace["_TRPSF_V1_STATE"]["last_load_ok"] is True


def test_patched_loader_without_registry_lock_blocks_before_read(tmp_path):
    reads = []
    normalizations = []
    namespace = {
        "Path": Path,
        "central_trade_registry": SimpleNamespace(
            _lock=None,
            _normalize_registry=lambda registry: normalizations.append(
                registry
            ),
        ),
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: tmp_path / "trade_registry.json",
        "_trpsf_v1_read_json": lambda path: reads.append(path),
    }
    _compile(
        [
            "_trpsf_v1_registry_lock",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )

    with pytest.raises(
        RuntimeError, match="TRADE_REGISTRY_PERSISTENCE_UNAVAILABLE"
    ):
        namespace["_trpsf_v1_patched_load_registry"]()

    assert reads == []
    assert normalizations == []
    assert namespace["_TRPSF_V1_STATE"]["last_load_ok"] is False


def test_patched_loader_falls_back_to_single_legacy_source_without_writes(tmp_path):
    active = tmp_path / "trade_registry.json"
    legacy = tmp_path / "legacy_registry.json"
    legacy.write_text(
        json.dumps({"open_trades": {}, "closed_trades": []}),
        encoding="utf-8",
    )
    writes = []

    def read_json(path):
        path = Path(path)
        if not path.exists():
            return None
        if path == legacy:
            return json.loads(path.read_text(encoding="utf-8"))
        if path == active:
            return None
        pytest.fail(f"unexpected read path: {path}")

    registry = SimpleNamespace(
        TRADE_REGISTRY_FILE=tmp_path / "old-registry.json",
        _lock=threading.RLock(),
        _normalize_registry=lambda registry: registry,
        load_registry=lambda: None,
        save_registry=lambda registry: True,
    )
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": registry,
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {
            "patched": False,
            "migration_done": False,
            "active_file": None,
            "original_registry_file": None,
            "legacy_files": [],
            "last_status": None,
            "last_load_ok": None,
            "last_write_ok": None,
            "last_error": None,
            "migrated_from_legacy": False,
        },
        "_TRPSF_V1_ORIGINAL_LOAD_REGISTRY": None,
        "_TRPSF_V1_ORIGINAL_SAVE_REGISTRY": None,
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [legacy],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": lambda *args, **kwargs: writes.append((args, kwargs)) or True,
        "TRADE_REGISTRY_IMPORT_ERROR": None,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "_trpsf_v1_now": lambda: "fixed",
    }
    _compile([
        "_trpsf_v1_registry_lock",
        "_trpsf_v1_registry_shape_errors",
        "_trpsf_v1_temporary_registry_source",
        "_trpsf_v1_apply_patch",
        "_trpsf_v1_patched_load_registry",
        "_trpsf_v1_patched_save_registry",
    ], namespace)

    status = namespace["_trpsf_v1_apply_patch"](run_bootstrap=False, force=False)

    assert status["status"] == "PATCH_INSTALLED_MIGRATION_PENDING"
    assert status["write_required"] is False
    assert status["write_performed"] is False
    assert writes == []

    registry_data = namespace["_trpsf_v1_patched_load_registry"]()

    assert registry_data == {"open_trades": {}, "closed_trades": []}
    assert namespace["_TRPSF_V1_STATE"]["temporary_read_source"] == str(legacy)
    assert namespace["_TRPSF_V1_STATE"]["temporary_read_only"] is True
    assert namespace["_TRPSF_V1_STATE"]["write_allowed"] is False
    assert writes == []


def test_patched_loader_blocks_on_ambiguous_legacy_sources(tmp_path):
    active = tmp_path / "trade_registry.json"
    first = tmp_path / "legacy_first.json"
    second = tmp_path / "legacy_second.json"
    first.write_text(
        json.dumps({"open_trades": {}, "closed_trades": []}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"open_trades": {}, "closed_trades": [{"trade_id": "X"}]}),
        encoding="utf-8",
    )
    reads = []

    def read_json(path):
        path = Path(path)
        reads.append(path)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    writes = []
    registry = SimpleNamespace(
        TRADE_REGISTRY_FILE=tmp_path / "old-registry.json",
        _lock=threading.RLock(),
        _normalize_registry=lambda registry: registry,
    )
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": registry,
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [first, second],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": lambda *args, **kwargs: pytest.fail(
            "writer reached while testing ambiguous legacy fallback"
        ),
        "_trpsf_v1_registry_shape_errors": lambda registry: [] if isinstance(registry, dict) else ["REGISTRY_NOT_OBJECT"],
    }
    _compile(
        [
            "_trpsf_v1_registry_lock",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_temporary_registry_source",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )

    with pytest.raises(RuntimeError, match="TRADE_REGISTRY_PERSISTENCE_UNAVAILABLE"):
        namespace["_trpsf_v1_patched_load_registry"]()

    assert namespace["_TRPSF_V1_STATE"]["last_error"] == "REGISTRY_MIGRATION_SOURCE_AMBIGUOUS"
    assert writes == []
    assert first in reads and second in reads


def test_patched_loader_blocks_when_no_registry_source_available(tmp_path):
    active = tmp_path / "trade_registry.json"

    registry = SimpleNamespace(
        TRADE_REGISTRY_FILE=tmp_path / "old-registry.json",
        _lock=threading.RLock(),
        _normalize_registry=lambda registry: registry,
    )
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": registry,
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [],
        "_trpsf_v1_read_json": lambda path: None,
        "_trpsf_v1_atomic_write_json": lambda *args, **kwargs: pytest.fail(
            "writer reached while testing no source fallback"
        ),
    }
    _compile(
        [
            "_trpsf_v1_registry_lock",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_temporary_registry_source",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )

    with pytest.raises(RuntimeError, match="TRADE_REGISTRY_PERSISTENCE_UNAVAILABLE"):
        namespace["_trpsf_v1_patched_load_registry"]()

    assert namespace["_TRPSF_V1_STATE"]["last_error"] == "NO_REGISTRY_SOURCES"


def test_patched_loader_uses_active_registry_when_valid(tmp_path):
    active = tmp_path / "trade_registry.json"
    legacy = tmp_path / "legacy_registry.json"
    active.write_text(
        json.dumps({"open_trades": {}, "closed_trades": []}),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps({"open_trades": {"x": {"trade_id": "X"}}, "closed_trades": []}),
        encoding="utf-8",
    )
    reads = []

    def read_json(path):
        path = Path(path)
        reads.append(path)
        if not path.exists():
            return None
        if path == active:
            return json.loads(path.read_text(encoding="utf-8"))
        pytest.fail("legacy source should not be read when active exists")

    registry = SimpleNamespace(
        TRADE_REGISTRY_FILE=tmp_path / "old-registry.json",
        _lock=threading.RLock(),
        _normalize_registry=lambda registry: registry,
    )
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": registry,
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {"migration_done": True},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [legacy],
        "_trpsf_v1_read_json": read_json,
    }
    _compile(
        [
            "_trpsf_v1_registry_lock",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )

    registry_data = namespace["_trpsf_v1_patched_load_registry"]()

    assert registry_data == {"open_trades": {}, "closed_trades": []}
    assert namespace["_TRPSF_V1_STATE"]["temporary_read_source"] is None
    assert namespace["_TRPSF_V1_STATE"]["temporary_read_only"] is False
    assert namespace["_TRPSF_V1_STATE"]["write_allowed"] is True
    assert reads == [active]


def test_patched_loader_blocks_when_active_registry_is_corrupted(tmp_path):
    active = tmp_path / "trade_registry.json"
    legacy = tmp_path / "legacy_registry.json"
    active.write_text("{invalid_json}", encoding="utf-8")
    legacy.write_text(
        json.dumps({"open_trades": {}, "closed_trades": []}),
        encoding="utf-8",
    )
    reads = []

    def read_json(path):
        reads.append(Path(path))
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    registry = SimpleNamespace(
        TRADE_REGISTRY_FILE=tmp_path / "old-registry.json",
        _lock=threading.RLock(),
        _normalize_registry=lambda registry: registry,
    )
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": registry,
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [legacy],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": lambda *args, **kwargs: pytest.fail(
            "writer reached while testing corrupted active registry"
        ),
    }
    _compile(
        [
            "_trpsf_v1_registry_lock",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )

    with pytest.raises(RuntimeError, match="TRADE_REGISTRY_PERSISTENCE_UNAVAILABLE"):
        namespace["_trpsf_v1_patched_load_registry"]()

    assert namespace["_TRPSF_V1_STATE"]["last_error"] == "ACTIVE_REGISTRY_INVALID"
    assert reads == [active]


def test_patched_save_registry_blocks_before_active_file_is_created(tmp_path):
    active = tmp_path / "trade_registry.json"
    writes = []
    namespace = {
        "Path": Path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_atomic_write_json": lambda *args, **kwargs: writes.append((args, kwargs)) or True,
        "_trpsf_v1_registry_lock": lambda: threading.RLock(),
        "central_trade_registry": SimpleNamespace(
            _normalize_registry=lambda payload: payload,
        ),
    }
    _compile(["_trpsf_v1_patched_save_registry"], namespace)

    result = namespace["_trpsf_v1_patched_save_registry"](
        {"open_trades": {}, "closed_trades": []}
    )

    assert result is False
    assert writes == []
    assert namespace["_TRPSF_V1_STATE"]["last_error"] == "ACTIVE_REGISTRY_UNAVAILABLE"


def test_patched_save_registry_uses_active_after_migration(tmp_path):
    active = tmp_path / "trade_registry.json"
    active.write_text(
        json.dumps({"open_trades": {}, "closed_trades": []}),
        encoding="utf-8",
    )
    writes = []

    def atomic_write_json(path, payload):
        writes.append((Path(path), payload))
        return True

    registry = SimpleNamespace(
        _normalize_registry=lambda payload: payload,
    )
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": registry,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_atomic_write_json": atomic_write_json,
        "_trpsf_v1_registry_lock": lambda: threading.RLock(),
        "_trpsf_v1_now": lambda: "fixed",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
    }
    _compile([
        "_trpsf_v1_registry_shape_errors",
        "_trpsf_v1_patched_save_registry",
    ], namespace)

    result = namespace["_trpsf_v1_patched_save_registry"](
        {"open_trades": {}, "closed_trades": []}
    )

    assert result is True
    assert writes == [(active, {"open_trades": {}, "closed_trades": [], "updated_at": "fixed", "storage_fix_version": "test-v1"})]


def test_bootstrap_without_registry_lock_blocks_before_filesystem_io(tmp_path):
    io_calls = []
    namespace = {
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_registry_lock": lambda: None,
        "_trpsf_v1_active_file": lambda: io_calls.append("active_file")
        or (tmp_path / "trade_registry.json"),
        "_trpsf_v1_read_json": lambda path: io_calls.append("read"),
        "_trpsf_v1_atomic_write_json": lambda path, payload: io_calls.append(
            "write"
        ),
        "_trpsf_v1_now": lambda: "fixed",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
    }
    _compile(["_trpsf_v1_bootstrap_registry"], namespace)

    result = namespace["_trpsf_v1_bootstrap_registry"](force=True)

    assert result["status"] == "REGISTRY_LOCK_UNAVAILABLE"
    assert result["write_performed"] is False
    assert result["closed_history_identity_merge"]["safe_to_commit"] is False
    assert io_calls == []


def test_bootstrap_without_lock_resolver_blocks_before_filesystem_io(tmp_path):
    io_calls = []
    namespace = {
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: io_calls.append("active_file")
        or (tmp_path / "trade_registry.json"),
        "_trpsf_v1_read_json": lambda path: io_calls.append("read"),
        "_trpsf_v1_atomic_write_json": lambda path, payload: io_calls.append(
            "write"
        ),
        "_trpsf_v1_now": lambda: "fixed",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
    }
    _compile(["_trpsf_v1_bootstrap_registry"], namespace)

    result = namespace["_trpsf_v1_bootstrap_registry"](force=True)

    assert result["status"] == "REGISTRY_LOCK_UNAVAILABLE"
    assert result["write_performed"] is False
    assert io_calls == []


def test_patched_save_without_lock_resolver_never_writes(tmp_path):
    writes = []
    namespace = {
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: tmp_path / "trade_registry.json",
        "_trpsf_v1_atomic_write_json": lambda path, payload: writes.append(
            (path, payload)
        ),
        "central_trade_registry": SimpleNamespace(
            _normalize_registry=lambda payload: payload
        ),
    }
    _compile(["_trpsf_v1_patched_save_registry"], namespace)

    assert (
        namespace["_trpsf_v1_patched_save_registry"](
            {"open_trades": {}, "closed_trades": []}
        )
        is False
    )
    assert writes == []
    assert namespace["_TRPSF_V1_STATE"]["last_error"] == (
        "REGISTRY_LOCK_UNAVAILABLE"
    )


@pytest.mark.parametrize(
    ("function_name", "expected_status"),
    [
        (
            "registry_persistence_v1_snapshot",
            "SNAPSHOT_BLOCKED_REGISTRY_LOCK_UNAVAILABLE",
        ),
        (
            "registry_persistence_v1_restore_from_latest_snapshot",
            "RESTORE_BLOCKED_REGISTRY_LOCK_UNAVAILABLE",
        ),
    ],
)
def test_snapshot_and_restore_commit_block_before_read_without_lock(
    function_name, expected_status
):
    namespace = {
        "central_trade_registry": SimpleNamespace(_lock=None),
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
    }
    _compile([function_name], namespace)

    result = namespace[function_name](commit=True)

    assert result["status"] == expected_status
    assert (
        result.get("committed") is False
        or result["snapshot_save"]["committed"] is False
    )


class _Args(dict):
    def get(self, key, default=None):
        return super().get(key, default)


@pytest.mark.parametrize(
    ("function_name", "query"),
    [
        ("registry_persistence_v1_route", {"commit": "true"}),
        ("registry_persistence_v1_route", {"restore": "true"}),
        (
            "registry_persistence_v12_closed_recovery_route",
            {"commit": "true"},
        ),
    ],
)
def test_legacy_get_write_flags_are_blocked_before_any_writer(
    function_name, query
):
    calls = []
    namespace = {
        "request": SimpleNamespace(args=_Args(query)),
        "_rp_v1_bool": lambda value, default=False: str(
            value or ""
        ).lower()
        in {"1", "true", "yes"},
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "registry_persistence_v1_snapshot": lambda **kwargs: calls.append(
            ("snapshot", kwargs)
        ),
        "registry_persistence_v1_restore_from_latest_snapshot": (
            lambda **kwargs: calls.append(("restore", kwargs))
        ),
        "registry_persistence_v12_recover_closed_trade_from_params": (
            lambda **kwargs: calls.append(("recover", kwargs))
        ),
    }
    _compile([function_name], namespace)

    payload, status, headers = namespace[function_name]()

    assert status == 400
    assert payload["status"] == "GET_IS_STRICTLY_READ_ONLY"
    assert payload["write_executed"] is False
    assert calls == []
    assert headers["Cache-Control"] == "no-store"


def test_closed_identity_audit_rejects_malformed_registry_before_merge():
    merge_calls = []
    namespace = {
        "central_trade_registry": SimpleNamespace(
            load_registry_raw_read_only=lambda: {
                "open_trades": {},
                "closed_trades": [
                    {"trade_id": "valid-shaped-row"},
                    "malformed-row",
                ],
            },
            merge_closed_trade_records=lambda rows: merge_calls.append(rows),
        )
    }
    _compile(
        [
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "trade_registry_closed_identity_audit_v1",
        ],
        namespace,
    )

    result = namespace["trade_registry_closed_identity_audit_v1"]()

    assert result["status"] == "CLOSED_IDENTITY_AUDIT_INVALID_REGISTRY_SHAPE"
    assert result["reason"] == "READ_ONLY_REGISTRY_INVALID_SHAPE"
    assert result["source_shape_errors"] == [
        "CLOSED_TRADES_INVALID_RECORD"
    ]
    assert result["migration_compatible"] is False
    assert result["safe_to_commit"] is False
    assert result["read_only"] is True
    assert result["write_executed"] is False
    assert merge_calls == []
