import json

import pytest

import executive_policy_learning as learning


@pytest.mark.parametrize(
    ("offset", "source_bytes", "expected_error"),
    [
        (60, b'{"code":"NEW"}\n', "TIMELINE_CURSOR_PAST_EOF"),
        (-1, b'{"code":"NEW"}\n', "TIMELINE_CURSOR_INVALID"),
        (60, None, "TIMELINE_CURSOR_PAST_EOF"),
    ],
)
def test_invalid_timeline_cursor_fails_closed_without_rewriting_stats(
    tmp_path, monkeypatch, offset, source_bytes, expected_error
):
    timeline = tmp_path / "timeline.jsonl"
    if source_bytes is not None:
        timeline.write_bytes(source_bytes)
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"timeline_offset": offset, "events_processed": 8}),
        encoding="utf-8",
    )
    stats_path = tmp_path / "stats.json"
    stats_bytes = json.dumps(
        {"policies": {"P1": {"events": 8}}, "summary": {"policy_count": 1}},
        sort_keys=True,
    ).encode("utf-8")
    stats_path.write_bytes(stats_bytes)
    log_path = tmp_path / "learning.jsonl"

    monkeypatch.setattr(learning, "TIMELINE_FILE", timeline)
    monkeypatch.setattr(learning, "STATE_FILE", state_path)
    monkeypatch.setattr(learning, "STATS_FILE", stats_path)
    monkeypatch.setattr(learning, "LOG_FILE", log_path)

    result = learning.run_executive_policy_learning(commit=True)

    assert result["ok"] is False
    assert result["error"] == expected_error
    assert result["old_offset"] == offset
    assert result["new_offset"] == offset
    assert result["events_processed"] == 0
    assert stats_path.read_bytes() == stats_bytes
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["timeline_offset"] == offset
    assert state["last_error"] == expected_error
    assert log_path.exists()
    health = learning.get_executive_policy_learning_health()
    assert health["ok"] is False
    assert health["status"] == "SOURCE_CHANGED"


def test_missing_timeline_at_zero_cursor_remains_waiting_not_error(tmp_path, monkeypatch):
    timeline = tmp_path / "timeline.jsonl"
    monkeypatch.setattr(learning, "TIMELINE_FILE", timeline)
    monkeypatch.setattr(learning, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(learning, "STATS_FILE", tmp_path / "stats.json")
    monkeypatch.setattr(learning, "LOG_FILE", tmp_path / "learning.jsonl")

    result = learning.run_executive_policy_learning(commit=False)

    assert result["ok"] is True
    assert result["events_processed"] == 0
    assert result["new_offset"] == 0


def test_cursor_at_or_before_current_eof_continues_normally(tmp_path, monkeypatch):
    timeline = tmp_path / "timeline.jsonl"
    timeline.write_bytes(b'{"code":"POLICY_A"}\n')
    monkeypatch.setattr(learning, "TIMELINE_FILE", timeline)
    monkeypatch.setattr(learning, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(learning, "STATS_FILE", tmp_path / "stats.json")
    monkeypatch.setattr(learning, "LOG_FILE", tmp_path / "learning.jsonl")

    result = learning.run_executive_policy_learning(commit=False)

    assert result["ok"] is True
    assert "error" not in result
    assert result["new_offset"] == timeline.stat().st_size


def test_restored_original_timeline_recovers_without_cursor_reset(tmp_path, monkeypatch):
    timeline = tmp_path / "timeline.jsonl"
    first = b'{"code":"POLICY_A","event":1}\n'
    second = b'{"code":"POLICY_A","event":2}\n'
    third = b'{"code":"POLICY_A","event":3}\n'
    original = first + second + third
    saved_offset = len(first + second)
    timeline.write_bytes(first)
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"timeline_offset": saved_offset, "events_processed": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(learning, "TIMELINE_FILE", timeline)
    monkeypatch.setattr(learning, "STATE_FILE", state_path)
    monkeypatch.setattr(learning, "STATS_FILE", tmp_path / "stats.json")
    monkeypatch.setattr(learning, "LOG_FILE", tmp_path / "learning.jsonl")

    blocked = learning.run_executive_policy_learning(commit=True)
    assert blocked["error"] == "TIMELINE_CURSOR_PAST_EOF"
    assert json.loads(state_path.read_text(encoding="utf-8"))["timeline_offset"] == saved_offset

    timeline.write_bytes(original)
    recovered = learning.run_executive_policy_learning(commit=True)

    assert recovered["ok"] is True
    assert recovered["events_processed"] == 1
    assert recovered["old_offset"] == saved_offset
    assert recovered["new_offset"] == len(original)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["timeline_offset"] == len(original)
    assert state["last_error"] is None
    assert learning.get_executive_policy_learning_health()["ok"] is True
