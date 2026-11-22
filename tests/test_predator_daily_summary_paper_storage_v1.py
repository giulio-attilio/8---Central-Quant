import ast
import json
from pathlib import Path

import predator_daily_summary


def test_predator_paper_event_append_uses_shared_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("RENDER", raising=False)

    result = predator_daily_summary.append_predator_event(
        {"event": "PAPER_TEST", "symbol": "SYNTHETIC"}
    )

    assert result["ok"] is True
    event_path = tmp_path / "predator_paper_events.jsonl"
    rows = [line for line in event_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1
    assert json.loads(rows[0])["event"] == "PAPER_TEST"


def test_predator_paper_event_append_fails_closed_outside_render_data_mount(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path / "ephemeral"))
    monkeypatch.setenv("RENDER", "true")

    result = predator_daily_summary.append_predator_event(
        {"event": "PAPER_TEST", "symbol": "SYNTHETIC"}
    )

    assert result["ok"] is False
    assert result["status"] == "WRITE_ERROR"
    assert not (tmp_path / "ephemeral").exists()


def test_predator_paper_event_writer_has_no_direct_path_open_or_mkdir():
    source = (Path(__file__).resolve().parents[1] / "predator_daily_summary.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "append_predator_event"
    )
    calls = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
        elif isinstance(node.func, ast.Name):
            calls.add(node.func.id)

    assert "append_paper_text" in calls
    assert "mkdir" not in calls
    assert "open" not in calls


def test_predator_event_log_read_fails_closed_when_storage_guard_rejects_existing_path(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.setenv("RENDER", "true")
    event_path = tmp_path / "predator_paper_events.jsonl"
    event_path.write_text('{"event":"SYNTHETIC"}\n', encoding="utf-8")
    assert event_path.exists()

    def reject_event_source(path):
        if Path(path) == event_path:
            raise OSError("PAPER_SYMLINK_REJECTED")
        return False

    monkeypatch.setattr(predator_daily_summary, "paper_file_exists", reject_event_source)

    result = predator_daily_summary.read_predator_event_log()

    assert result["ok"] is False
    assert result["status"] == "EVENT_LOG_READ_ERROR"
    assert result["events"] == []
