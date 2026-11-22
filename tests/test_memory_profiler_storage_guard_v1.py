from __future__ import annotations

import ast
import json
from pathlib import Path

import memory_profiler_v1 as profiler
from paper_state_storage import resolve_paper_data_dir


ROOT = Path(__file__).resolve().parents[1]


def _set_profiler_paths(monkeypatch, data_dir: Path) -> None:
    monkeypatch.setattr(profiler, "DATA_DIR", data_dir)
    monkeypatch.setattr(profiler, "SNAPSHOT_FILE", data_dir / "memory_profiler_snapshots.jsonl")
    monkeypatch.setattr(profiler, "STATE_FILE", data_dir / "memory_profiler_state.json")
    monkeypatch.setattr(profiler, "ERROR_FILE", data_dir / "memory_profiler_error.log")


def test_data_dir_resolution_prefers_central_then_render_data(monkeypatch, tmp_path):
    central = tmp_path / "central"
    render_data = tmp_path / "render-data"
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(central))
    monkeypatch.setenv("DATA_DIR", str(render_data))

    assert resolve_paper_data_dir(profiler.__file__) == central

    monkeypatch.delenv("CENTRAL_DATA_DIR")
    assert resolve_paper_data_dir(profiler.__file__) == render_data


def test_snapshot_and_state_use_guarded_persistent_helpers(monkeypatch, tmp_path):
    data_dir = tmp_path / "persistent"
    _set_profiler_paths(monkeypatch, data_dir)
    snapshot = {"ok": True, "reason": "test", "memory": {"rss_mb": 12.5}}

    profiler._append_snapshot(snapshot)
    profiler._save_state(snapshot)

    assert json.loads(profiler.SNAPSHOT_FILE.read_text(encoding="utf-8")) == snapshot
    stored_state = json.loads(profiler.STATE_FILE.read_text(encoding="utf-8"))
    assert stored_state["last_snapshot"] == snapshot
    assert Path(stored_state["snapshot_file"]) == profiler.SNAPSHOT_FILE
    assert Path(stored_state["state_file"]) == profiler.STATE_FILE


def test_missing_persistent_mount_fails_closed_without_creating_files(monkeypatch, tmp_path):
    data_dir = tmp_path / "unavailable"
    _set_profiler_paths(monkeypatch, data_dir)
    monkeypatch.setattr(profiler, "_ensure_data_dir", lambda: False)

    try:
        profiler._append_snapshot({"ok": True})
    except OSError as exc:
        assert str(exc) == "MEMORY_PROFILER_DATA_DIR_NOT_PERSISTENT"
    else:  # pragma: no cover - assertion aid
        raise AssertionError("snapshot write did not fail closed")

    try:
        profiler._save_state({"ok": True})
    except OSError as exc:
        assert str(exc) == "MEMORY_PROFILER_DATA_DIR_NOT_PERSISTENT"
    else:  # pragma: no cover - assertion aid
        raise AssertionError("state write did not fail closed")

    assert not data_dir.exists()


def test_snapshot_reader_returns_only_complete_jsonl_rows(monkeypatch, tmp_path):
    data_dir = tmp_path / "persistent"
    _set_profiler_paths(monkeypatch, data_dir)
    data_dir.mkdir()
    profiler.SNAPSHOT_FILE.write_bytes(b'{"id":1}\n{"id":2}\n{"incomplete":')

    assert profiler._read_last_snapshots(limit=4) == [{"id": 1}, {"id": 2}]


def test_profiler_storage_functions_do_not_use_raw_path_io():
    tree = ast.parse((ROOT / "memory_profiler_v1.py").read_text(encoding="utf-8"))
    names = {"_maybe_trim_snapshot_file", "_read_last_snapshots", "_append_snapshot", "_save_state", "_memory_loop"}
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    }
    assert set(functions) == names

    for name, function in functions.items():
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        called = {
            node.func.id if isinstance(node.func, ast.Name)
            else node.func.attr if isinstance(node.func, ast.Attribute)
            else ""
            for node in calls
        }
        assert "open" not in called, name
        assert "write_text" not in called, name
        assert "read_text" not in called, name

    source = (ROOT / "memory_profiler_v1.py").read_text(encoding="utf-8")
    assert '"/opt/render/project/src/data"' not in source
    assert "resolve_paper_data_dir(__file__)" in source
