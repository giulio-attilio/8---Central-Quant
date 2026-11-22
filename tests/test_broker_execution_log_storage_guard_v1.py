import ast
import importlib.util
import os
from pathlib import Path
import sys
import types

import pytest

if importlib.util.find_spec("ccxt") is None:
    # The tests exercise local log helpers only; keep the import offline and
    # do not install or emulate any exchange operation.
    ccxt_stub = types.ModuleType("ccxt")
    ccxt_stub.bingx = lambda **_kwargs: None
    sys.modules["ccxt"] = ccxt_stub

import broker


def test_execution_and_audit_logs_append_and_read_from_explicit_local_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    execution_path = tmp_path / "executions.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(broker, "EXECUTIONS_LOG_FILE", str(execution_path))
    monkeypatch.setattr(broker, "EXECUTION_AUDIT_LOG_FILE", str(audit_path))

    assert broker.log_execution_event({"event": "DRY_RUN_TEST"}) is True
    assert broker.log_execution_audit_event({"event": "AUDIT_TEST"}) is True
    assert broker._read_jsonl_file(execution_path, limit=1)[0]["event"] == "DRY_RUN_TEST"
    assert broker._read_jsonl_file(audit_path, limit=1)[0]["event"] == "AUDIT_TEST"


def test_render_rejects_ephemeral_broker_log_writes_and_reads(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("Render mount enforcement is POSIX-specific")
    monkeypatch.setenv("RENDER", "true")
    path = tmp_path / "execution.jsonl"
    monkeypatch.setattr(broker, "EXECUTIONS_LOG_FILE", str(path))

    assert broker.log_execution_event({"event": "MUST_NOT_PERSIST"}) is False
    assert path.exists() is False
    result = broker._read_jsonl_file(path, limit=1)
    assert len(result) == 1
    assert result[0]["ok"] is False


@pytest.mark.parametrize(
    "getter,primary,legacy",
    [
        ("get_executions_log", "EXECUTIONS_LOG_FILE", "BROKER_LEGACY_EXECUTIONS_LOG_FILE"),
        ("get_execution_audit_log", "EXECUTION_AUDIT_LOG_FILE", "BROKER_LEGACY_AUDIT_LOG_FILE"),
    ],
)
def test_render_does_not_read_ephemeral_legacy_broker_logs(
    monkeypatch, tmp_path, getter, primary, legacy
):
    monkeypatch.setenv("RENDER", "true")
    primary_path = tmp_path / "primary.jsonl"
    monkeypatch.setattr(broker, primary, str(primary_path))
    calls = []

    def fake_read(path, **kwargs):
        calls.append(str(path))
        return []

    monkeypatch.setattr(broker, "_read_jsonl_file", fake_read)
    getattr(broker, getter)(limit=2)

    assert calls == [str(primary_path)]
    assert str(getattr(broker, legacy)) not in calls


def test_broker_execution_log_io_uses_shared_helpers():
    source = Path(broker.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    relevant = [
        functions[name]
        for name in (
            "log_execution_event",
            "log_execution_audit_event",
            "_read_jsonl_file",
        )
    ]
    direct_io = [
        node for function in relevant for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"open", "mkdir", "read_text", "write_text"}
    ]

    assert direct_io == []
