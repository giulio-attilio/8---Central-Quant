from __future__ import annotations

import json
import threading

import pytest

import history_manager


def _configure(monkeypatch, tmp_path):
    monkeypatch.setattr(history_manager, "CLOSED_TRADES_FILE", tmp_path / "closed_trades.jsonl")
    monkeypatch.setattr(history_manager, "CLOSED_TRADE_KEY_INDEX_FILE", tmp_path / "closed_trade_key_index_v1.json")
    monkeypatch.setattr(history_manager, "ensure_history_files", lambda: None)
    monkeypatch.setattr(history_manager, "_closed_trade_record_from_event", lambda item: dict(item))


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_index_rebuilds_once_then_avoids_full_scan(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    first = history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    assert first["closed_trade_key_index_rebuilt"] is True
    assert first["full_history_scan_performed"] is True
    assert first["closed_trade_key_index_write_success"] is True
    assert first["closed_trade_key_index_valid"] is True
    monkeypatch.setattr(history_manager, "_load_closed_trade_keys", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("scan")))
    second = history_manager.append_closed_trade({"uid": "TWO", "trade_id": "TWO"})
    assert second["ok"] is True
    assert second["full_history_scan_performed"] is False
    assert len(_rows(history_manager.CLOSED_TRADES_FILE)) == 2


def test_index_deduplicates_after_restart_and_recovers_corruption(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    duplicate = history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    assert duplicate["dedup"] is True and duplicate["duplicate_detected"] is True
    history_manager.CLOSED_TRADE_KEY_INDEX_FILE.write_text("not-json", encoding="utf-8")
    recovered = history_manager.append_closed_trade({"uid": "TWO", "trade_id": "TWO"})
    assert recovered["closed_trade_key_index_rebuilt"] is True
    assert len(_rows(history_manager.CLOSED_TRADES_FILE)) == 2


def test_threads_and_distinct_identities_preserve_canonical_rows(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    results = []
    threads = [threading.Thread(target=lambda: results.append(history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"}))) for _ in range(4)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    history_manager.append_closed_trade({"uid": "TWO", "trade_id": "TWO"})
    assert len(_rows(history_manager.CLOSED_TRADES_FILE)) == 2
    assert sum(bool(result.get("dedup")) for result in results) == 3


@pytest.mark.parametrize(
    "mutate",
    [
        lambda index: index.update({"version": 2}),
        lambda index: index.update({"key_count": 99}),
        lambda index: index.update({"keys_checksum_sha256": "0" * 64}),
        lambda index: index.update({"closed_trades_size": -1}),
        lambda index: index.update({"closed_trades_mtime_ns": -1}),
    ],
)
def test_valid_json_index_with_invalid_integrity_metadata_rebuilds(monkeypatch, tmp_path, mutate):
    _configure(monkeypatch, tmp_path)
    history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    index_path = history_manager.CLOSED_TRADE_KEY_INDEX_FILE
    index = json.loads(index_path.read_text(encoding="utf-8"))
    mutate(index)
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = history_manager.append_closed_trade({"uid": "TWO", "trade_id": "TWO"})

    assert result["closed_trade_key_index_rebuilt"] is True
    assert result["closed_trade_key_index_valid"] is True
    assert result["closed_trade_key_index_integrity_error"] == "ValueError"
    assert len(_rows(history_manager.CLOSED_TRADES_FILE)) == 2


def test_stream_rebuild_ignores_tail_limit_and_invalid_lines(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    path = history_manager.CLOSED_TRADES_FILE
    path.write_text(
        "\n".join(json.dumps({"uid": f"ROW-{number}", "trade_id": f"ROW-{number}"}) for number in range(12))
        + "\n{partial\n"
        + json.dumps({"uid": "LAST", "trade_id": "LAST"})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(history_manager, "_read_jsonl_tail", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tail read")))

    result = history_manager.append_closed_trade({"uid": "NEW", "trade_id": "NEW"})

    assert result["full_history_scan_performed"] is True
    assert result["closed_trade_rebuild_invalid_lines"] == 1
    assert len([line for line in path.read_text(encoding="utf-8").splitlines() if line]) == 15


def test_index_write_failure_after_append_rebuilds_without_duplicate(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(history_manager, "_write_closed_trade_key_index", lambda _keys: False)
    first = history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    assert first["ok"] is True
    assert first["closed_trade_key_index_write_success"] is False
    assert first["closed_trade_key_index_valid"] is False
    assert len(_rows(history_manager.CLOSED_TRADES_FILE)) == 1

    monkeypatch.undo()
    _configure(monkeypatch, tmp_path)
    duplicate = history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    assert duplicate["dedup"] is True
    assert duplicate["closed_trade_key_index_rebuilt"] is True
    assert len(_rows(history_manager.CLOSED_TRADES_FILE)) == 1


def test_failed_canonical_append_does_not_add_key_or_telemetry_to_record(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(history_manager, "_append_jsonl", lambda *_args, **_kwargs: False)
    failed = history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    assert failed["ok"] is False
    assert failed["dedup"] is False
    assert failed["closed_trade_key_index_valid"] is True
    assert not history_manager.CLOSED_TRADES_FILE.exists()

    monkeypatch.undo()
    _configure(monkeypatch, tmp_path)
    written = history_manager.append_closed_trade({"uid": "ONE", "trade_id": "ONE"})
    row = _rows(history_manager.CLOSED_TRADES_FILE)[0]
    assert written["ok"] is True
    assert {"ok", "dedup", "file", "trade_id", "bot", "symbol", "pnl_pct"}.issubset(written)
    assert not any(key.startswith("closed_trade_") or key == "duplicate_detected" for key in row)
