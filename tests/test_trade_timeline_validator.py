from __future__ import annotations

import copy
import json
import socket

import pytest

from trade_timeline_validator import COMPONENTS, REQUIRED_EVENTS, validate_trade_timeline


TRADE_ID = "TR-LIVE-1"


def event(name, second, **updates):
    row = {
        "trade_id": TRADE_ID,
        "event_type": name,
        "timestamp": f"2026-07-13T12:00:{second:02d}Z",
        "event_id": f"E-{name}-{second}",
    }
    row.update(updates)
    return row


def valid_sources():
    return {
        "registry": [{"trade_id": TRADE_ID, "status": "CLOSED", "symbol": "BTCUSDT", "side": "LONG", "entry": 100.0, "exit_price": 110.0, "qty": 1.0, "opened_at": "2026-07-13T12:00:05Z", "closed_at": "2026-07-13T12:00:10Z"}],
        "lifecycle": [event("SIGNAL_RECEIVED", 1), event("RISK_APPROVED", 2), event("LIFECYCLE_FINISHED", 12, status="CLOSED", symbol="BTCUSDT", side="LONG", entry=100.0, exit_price=110.0, quantity=1.0)],
        "history_manager": [event("EXECUTION_REQUESTED", 3), event("TP50", 7), event("BREAK_EVEN", 8), event("TRAILING_UPDATED", 9)],
        "execution_engine": [event("LIVE_ORDER_SENT", 4)],
        "execution_orchestrator": [event("PARTIAL_CLOSE", 9)],
        "broker": [event("BROKER_ACK", 5, status="CLOSED", symbol="BTCUSDT", side="LONG", entry_price=100.0, exit_price=110.0, quantity=1.0), event("LIVE_TRADE_CLOSED", 10)],
        "shadow_runtime": [event("SHADOW_VALIDATED", 13, status="CLOSED", symbol="BTCUSDT", side="LONG", entry=100.0, exit_price=110.0, quantity=1.0)],
        "timeline": [event("POSITION_OPEN", 6), event("REGISTRY_CLOSE", 11)],
        "telegram": [event("TELEGRAM_SENT", 6)],
    }


def test_complete_valid_live_flow_passes_without_side_effects(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: pytest.fail("network access"))
    sources = valid_sources()
    original = copy.deepcopy(sources)
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert report["result"] == "PASS"
    assert report["events_missing"] == []
    assert report["events_duplicated"] == []
    assert report["chronology"]["ordered"] is True
    assert report["divergences"] == []
    assert report["authorities"]["broker_access"] is False
    assert report["production_blocked"] is False
    assert sources == original


def test_missing_event_fails_and_names_event():
    sources = valid_sources()
    sources["execution_engine"] = []
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert report["result"] == "FAIL"
    assert "LIVE_ORDER_SENT" in report["events_missing"]


def test_duplicate_singleton_event_is_reported():
    sources = valid_sources()
    sources["execution_engine"].append(event("LIVE_ORDER_SENT", 4, event_id="SECOND"))
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    duplicate = next(item for item in report["events_duplicated"] if item["event"] == "LIVE_ORDER_SENT")
    assert duplicate["occurrences"] == 2
    assert report["result"] == "FAIL"


def test_distinct_trailing_updates_are_legitimate_repeated_events():
    sources = valid_sources()
    sources["history_manager"].append(event("TRAILING_UPDATED", 10, event_id="TRAIL-SECOND"))
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert not any(item["event"] == "TRAILING_UPDATED" for item in report["events_duplicated"])


def test_registry_broker_divergence_is_reported():
    sources = valid_sources()
    sources["broker"][0]["entry_price"] = 101.5
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert any(item["components"] == ["registry", "broker"] and item["field"] == "entry" for item in report["divergences"])
    assert report["result"] == "FAIL"


def test_lifecycle_shadow_divergence_is_reported():
    sources = valid_sources()
    sources["shadow_runtime"][0]["quantity"] = 0.5
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert any(item["components"] == ["lifecycle", "shadow_runtime"] and item["field"] == "quantity" for item in report["divergences"])
    assert report["result"] == "FAIL"


def test_absent_timeline_is_explicit_failure():
    sources = valid_sources()
    sources["timeline"] = []
    sources["history_manager"].extend([event("POSITION_OPEN", 6), event("REGISTRY_CLOSE", 11)])
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert report["components"]["timeline"]["status"] == "NO_EVIDENCE"
    assert report["summary"]["timeline_available"] is False
    assert report["result"] == "FAIL"


def test_source_reader_error_is_fail_open_and_does_not_escape():
    sources = valid_sources()

    def broken(_trade_id):
        raise OSError("read failed")

    sources["history_manager"] = broken
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert report["ok"] is True
    assert report["result"] == "FAIL"
    assert report["fail_open"] is True
    assert report["production_blocked"] is False
    assert report["components"]["history_manager"]["status"] == "ERROR"
    assert report["errors"][0]["error_type"] == "OSError"


def test_all_declared_components_have_status_even_when_unavailable():
    report = validate_trade_timeline(TRADE_ID, sources={"timeline": []})
    assert set(report["components"]) == set(COMPONENTS)
    assert set(REQUIRED_EVENTS).issuperset(report["events_missing"])


def test_default_paths_are_read_only_and_stream_jsonl(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    rows = [event(name, index + 1) for index, name in enumerate(REQUIRED_EVENTS)]
    (data / "timeline.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(data))
    before = sorted(path.name for path in data.iterdir())
    report = validate_trade_timeline(TRADE_ID)
    after = sorted(path.name for path in data.iterdir())
    assert report["components"]["timeline"]["records"] == len(rows)
    assert before == after == ["timeline.jsonl"]
