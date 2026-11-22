import ast
import importlib
import os
from pathlib import Path

import pytest


MODULES = (
    "executive_alert_manager",
    "event_bus",
    "policy_engine",
    "executive_policy_manager",
    "executive_policy_priority",
    "executive_policy_auto_release",
    "executive_policy_expiration",
    "executive_policy_timeline",
)

READERS = {
    "executive_alert_manager": "_read_json",
    "event_bus": "_read_json",
    "policy_engine": "_read_json",
    "executive_policy_manager": "_read_json",
    "executive_policy_priority": "_safe_read_json",
    "executive_policy_auto_release": "_safe_read_json",
    "executive_policy_expiration": "_safe_read_json",
    "executive_policy_timeline": "_safe_read_json",
}


def test_policy_state_modules_route_filesystem_access_through_shared_guard():
    root = Path(__file__).resolve().parents[1]
    for module_name in MODULES:
        source = (root / f"{module_name}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "resolve_paper_data_dir" in source, module_name
        assert "paper_data_mount_verified" in source, module_name
        assert "paper_file_exists" in source, module_name
        assert "read_paper_text" in source, module_name
        assert "write_json_atomically" in source, module_name
        assert "append_paper_text" in source, module_name

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id != "open", f"unguarded open in {module_name}:{node.lineno}"
            if isinstance(func, ast.Attribute):
                assert func.attr not in {
                    "open",
                    "read_text",
                    "write_text",
                    "touch",
                    "mkdir",
                }, f"unguarded Path I/O in {module_name}:{node.lineno}"
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr in {"replace", "remove", "unlink", "makedirs"}
                ):
                    raise AssertionError(f"unguarded os I/O in {module_name}:{node.lineno}")


@pytest.mark.parametrize("module_name", MODULES)
def test_policy_state_read_fails_closed_when_mount_guard_rejects_path(
    module_name, tmp_path, monkeypatch
):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "paper_data_mount_verified", lambda _path: False)
    reader = getattr(module, READERS[module_name])
    path = tmp_path / "must-not-read.json"

    with pytest.raises(OSError, match="PAPER_DATA_MOUNT_NOT_VERIFIED"):
        reader(str(path) if module_name == "executive_policy_manager" else path, {})

    assert not path.exists()


def test_trade_journal_and_learning_modules_route_io_through_shared_storage():
    root = Path(__file__).resolve().parents[1]
    modules = {
        "journal_manager": {
            "resolve_paper_data_dir",
            "ensure_paper_data_dir",
            "paper_file_exists",
            "read_paper_text",
            "read_paper_tail_lines",
            "open_paper_binary",
            "write_json_atomically",
            "append_paper_text",
        },
        "learning_engine": {
            "resolve_paper_data_dir",
            "paper_file_exists",
            "read_paper_text",
            "write_json_atomically",
            "append_paper_text",
        },
        "context_manager": {"resolve_paper_data_dir"},
    }
    forbidden_path_calls = {
        "open",
        "read_text",
        "write_text",
        "touch",
        "mkdir",
    }
    for module_name, required_helpers in modules.items():
        source = (root / f"{module_name}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert all(helper in source for helper in required_helpers), module_name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id != "open", f"unguarded open in {module_name}:{node.lineno}"
            if isinstance(func, ast.Attribute):
                assert func.attr not in forbidden_path_calls, (
                    f"unguarded Path I/O in {module_name}:{node.lineno}"
                )
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr in {"open", "replace", "remove", "unlink", "makedirs"}
                ):
                    raise AssertionError(f"unguarded os I/O in {module_name}:{node.lineno}")
