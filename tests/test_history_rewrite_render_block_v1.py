from __future__ import annotations

import json

import history_manager


def _assert_blocked(result, operation):
    assert result["ok"] is False
    assert result["status"] == "BLOCKED_STORAGE_GUARD_REQUIRED"
    assert result["reason"] == "DESCRIPTOR_ANCHORED_REWRITE_NOT_IMPLEMENTED"
    assert result["operation"] == operation
    assert result["committed"] is False
    assert result["safe_to_commit"] is False


def test_history_rotation_is_blocked_on_render_before_read_or_write(monkeypatch, tmp_path):
    source = tmp_path / "history_events.jsonl"
    original = b'{"event":"DEBUG","id":"keep-me"}\n'
    source.write_bytes(original)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(
        history_manager,
        "preview_history_events_rotation",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("preview must not run")),
    )

    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        path=source,
    )

    _assert_blocked(result, "history_events_rotation")
    assert source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]


def test_emergency_rotation_is_blocked_on_render_before_read_or_write(monkeypatch, tmp_path):
    source = tmp_path / "history_events.jsonl"
    original = b'{"event":"DEBUG","id":"keep-me"}\n'
    source.write_bytes(original)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(
        history_manager,
        "preview_history_events_emergency_rotation",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("preview must not run")),
    )

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        path=source,
    )

    _assert_blocked(result, "history_events_emergency_rotation")
    assert source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]


def test_closed_trade_rebuild_is_blocked_on_render_without_truncating(monkeypatch, tmp_path):
    target = tmp_path / "closed_trades.jsonl"
    original = b'{"trade_id":"preserve"}\n'
    target.write_bytes(original)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(history_manager, "CLOSED_TRADES_FILE", target)

    result = history_manager.rebuild_closed_trades_v4_from_events()

    _assert_blocked(result, "closed_trades_rebuild")
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]


def test_forced_closed_trade_backfill_is_blocked_on_render(monkeypatch, tmp_path):
    target = tmp_path / "closed_trades.jsonl"
    original = b'{"trade_id":"preserve"}\n'
    target.write_bytes(original)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(history_manager, "CLOSED_TRADES_FILE", target)

    result = history_manager.backfill_closed_trades_from_events(force=True)

    _assert_blocked(result, "closed_trades_forced_backfill")
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]


def test_incremental_closed_trade_backfill_is_not_blocked_by_render_guard(monkeypatch, tmp_path):
    target = tmp_path / "closed_trades.jsonl"
    target.write_text(json.dumps({"trade_id": "present"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(history_manager, "CLOSED_TRADES_FILE", target)
    monkeypatch.setattr(history_manager, "ensure_history_files", lambda: True)
    monkeypatch.setattr(history_manager, "_load_closed_trade_keys", lambda **_kwargs: {"present"})
    monkeypatch.setattr(history_manager, "load_events", lambda **_kwargs: [])
    monkeypatch.setattr(history_manager, "_count_jsonl", lambda _path: 1)

    result = history_manager.backfill_closed_trades_from_events(force=False)

    assert result["ok"] is True
    assert result["created"] == 0
    assert target.read_text(encoding="utf-8") == json.dumps({"trade_id": "present"}) + "\n"
