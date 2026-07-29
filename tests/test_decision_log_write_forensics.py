from __future__ import annotations

import ast
import json
import threading
from pathlib import Path

from flask import Flask

import decision_log_forensics as forensics


ROOT = Path(__file__).resolve().parents[1]


def _compile_writer(relative: str, function_name: str, namespace: dict):
    source = (ROOT / relative).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, f"<isolated-{function_name}>", "exec"), namespace)
    return namespace[function_name]


def _writer(relative: str, function_name: str, module_name: str):
    return _compile_writer(
        relative,
        function_name,
        {
            "__name__": module_name,
            "json": json,
            "Path": Path,
            "_json_default": str,
        },
    )


def _events(output: str):
    return [
        json.loads(line.split(" ", 1)[1])
        for line in output.splitlines()
        if line.startswith("DECISION_LOG_WRITE_FORENSICS ")
    ]


def test_main_writer_forensics_identifies_flask_route_and_hides_payload(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CENTRAL_DECISION_LOG_WRITE_FORENSICS_ENABLED", "true")
    writer = _writer("main.py", "_append_jsonl", "main")
    path = tmp_path / "decision_log.jsonl"
    secret = "decision-secret-must-not-appear"
    item = {
        "bot": "FALCON",
        "event": "RISK_DENY",
        "trade_id": "trade-1",
        "payload": {"token": secret},
    }
    app = Flask("decision-log-forensics")

    @app.route("/decision/write")
    def decision_write_route():
        assert writer(path, item) is True
        return {"ok": True}

    response = app.test_client().get("/decision/write")
    assert response.status_code == 200
    assert path.read_text(encoding="utf-8").splitlines() == [
        json.dumps(item, ensure_ascii=False, default=str)
    ]

    output = capsys.readouterr().out
    events = _events(output)
    assert len(events) == 1
    event = events[0]
    assert event["writer"] == "main._append_jsonl"
    assert event["route_endpoint"] == "decision_write_route"
    assert event["route_path"] == "/decision/write"
    assert event["bot"] == "FALCON"
    assert event["event_type"] == "RISK_DENY"
    assert event["decision_id"] == "trade-1"
    assert event["serialized_bytes"] == len(
        (json.dumps(item, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    )
    assert event["file_size_before"] in (None, 0)
    assert event["file_size_after"] == path.stat().st_size
    assert event["duplicate_detected"] is None
    assert event["write_success"] is True
    assert secret not in output


def test_history_writer_forensics_identifies_background_thread(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CENTRAL_DECISION_LOG_WRITE_FORENSICS_ENABLED", "true")
    writer = _writer("history_manager.py", "_append_jsonl_unlocked", "history_manager")
    path = tmp_path / "decision_log.jsonl"
    result = []

    def background_write():
        result.append(writer(path, {"bot": "PREDATOR", "event": "RISK_ALLOW"}))

    thread = threading.Thread(target=background_write, name="decision-log-background")
    thread.start()
    thread.join()

    assert result == [True]
    events = _events(capsys.readouterr().out)
    assert len(events) == 1
    event = events[0]
    assert event["writer"] == "history_manager._append_jsonl_unlocked"
    assert event["thread"] == "decision-log-background"
    assert event["route_endpoint"] is None
    assert event["route_path"] is None
    assert event["write_success"] is True


def test_forensics_failure_is_fail_open_and_writer_keeps_one_record(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CENTRAL_DECISION_LOG_WRITE_FORENSICS_ENABLED", "true")
    monkeypatch.setattr(
        forensics,
        "_safe_log",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("log unavailable")),
    )
    writer = _writer("main.py", "_append_jsonl", "main")
    path = tmp_path / "decision_log.jsonl"

    assert writer(path, {"bot": "FALCON", "event": "RISK_DENY"}) is True
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert _events(capsys.readouterr().out) == []


def test_forensics_module_has_no_history_reads_or_external_dependencies():
    source = (ROOT / "decision_log_forensics.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert imported.isdisjoint({"requests", "redis", "broker", "telegram", "flask"})
    assert ".read_text(" not in source
    assert ".readlines(" not in source
    assert ".read(" not in source
    assert called.isdisjoint({"connect", "post", "send_telegram", "create_order"})
