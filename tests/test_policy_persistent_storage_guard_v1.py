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
        "executive_policy_learning": {
            "resolve_paper_data_dir",
            "ensure_paper_data_dir",
            "paper_data_mount_verified",
            "open_paper_text",
            "write_json_atomically",
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


@pytest.mark.parametrize(
    "seed_function_name",
    ["seed_executive_policy_learning_events", "seed_policy_effect_decision"],
)
def test_policy_learning_seed_fails_closed_without_creating_unmounted_data_dir(
    seed_function_name, tmp_path, monkeypatch
):
    import executive_policy_learning as learning

    target = tmp_path / "would-be-ephemeral-data"
    monkeypatch.setattr(learning, "DATA_DIR", target)
    monkeypatch.setattr(learning, "TIMELINE_FILE", target / "timeline.jsonl")
    monkeypatch.setattr(learning, "DECISION_LOG_FILE", target / "decision.jsonl")
    monkeypatch.setattr(learning, "ensure_paper_data_dir", lambda _path: False)

    seed = getattr(learning, seed_function_name)
    with pytest.raises(OSError, match="POLICY_LEARNING_DATA_DIR_NOT_AVAILABLE"):
        seed(commit=True)

    assert not target.exists()


@pytest.mark.parametrize(
    ("seed_function_name", "writer_name"),
    [
        ("seed_executive_policy_learning_events", "_append_log"),
        ("seed_policy_effect_decision", "open_paper_text"),
    ],
)
def test_policy_learning_seed_check_only_performs_no_filesystem_writes(
    seed_function_name, writer_name, tmp_path, monkeypatch
):
    import executive_policy_learning as learning

    target = tmp_path / "check-only-data"
    monkeypatch.setattr(learning, "DATA_DIR", target)
    monkeypatch.setattr(learning, "TIMELINE_FILE", target / "timeline.jsonl")
    monkeypatch.setattr(learning, "LOG_FILE", target / "learning.jsonl")
    monkeypatch.setattr(learning, "DECISION_LOG_FILE", target / "decision.jsonl")
    monkeypatch.setattr(learning, "V2_LOG_FILE", target / "effect.jsonl")
    monkeypatch.setattr(
        learning,
        "ensure_paper_data_dir",
        lambda _path: pytest.fail("check-only must not initialize storage"),
    )
    calls = []
    monkeypatch.setattr(
        learning,
        writer_name,
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = getattr(learning, seed_function_name)(commit=False)

    assert result["ok"] is True
    assert result["commit"] is False
    assert calls == []
    assert not target.exists()


@pytest.mark.parametrize(
    "seed_function_name",
    ["seed_executive_policy_learning_events", "seed_policy_effect_decision"],
)
def test_policy_learning_seed_commit_uses_only_temporary_paper_storage(
    seed_function_name, tmp_path, monkeypatch
):
    import executive_policy_learning as learning

    monkeypatch.delenv("RENDER", raising=False)
    target = tmp_path / "paper-state"
    monkeypatch.setattr(learning, "DATA_DIR", target)
    monkeypatch.setattr(learning, "TIMELINE_FILE", target / "timeline.jsonl")
    monkeypatch.setattr(learning, "LOG_FILE", target / "learning.jsonl")
    monkeypatch.setattr(learning, "DECISION_LOG_FILE", target / "decision.jsonl")
    monkeypatch.setattr(learning, "V2_LOG_FILE", target / "effect.jsonl")

    result = getattr(learning, seed_function_name)(commit=True)

    assert result["ok"] is True
    assert result["commit"] is True
    assert target.is_dir()
    if seed_function_name == "seed_executive_policy_learning_events":
        assert len((target / "timeline.jsonl").read_text(encoding="utf-8").splitlines()) == 7
        assert (target / "learning.jsonl").is_file()
        assert not (target / "decision.jsonl").exists()
    else:
        assert len((target / "decision.jsonl").read_text(encoding="utf-8").splitlines()) == 1
        assert len((target / "effect.jsonl").read_text(encoding="utf-8").splitlines()) == 1
        assert not (target / "timeline.jsonl").exists()
