from __future__ import annotations

import copy
import json
import socket
import threading

import pytest

import live_trade_snapshot as snapshot_module
from live_trade_snapshot import GRACE_WINDOWS, build_live_trade_snapshot


TRADE_ID = "TR-FALCON-001"
BASE_TIME = 1_800_000_000.0


def _timeline(result="PASS", missing=None, divergences=None, warnings=None):
    return {
        "result": result,
        "valid": result == "PASS",
        "components": {},
        "events_found": [],
        "events_missing": list(missing or []),
        "events_duplicated": [],
        "divergences": list(divergences or []),
        "latencies": [],
        "warnings": list(warnings or []),
        "errors": [],
    }


def _record(**updates):
    item = {
        "trade_id": TRADE_ID,
        "lifecycle_id": "LC-001",
        "bot": "FALCON",
        "setup": "ORB",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "LIVE",
    }
    item.update(updates)
    return item


def _sources(*, registry=None, lifecycle=None, broker=None, external=None):
    return {
        "registry": list(registry or []),
        "lifecycle": list(lifecycle or []),
        "history_manager": [],
        "execution_engine": [],
        "execution_orchestrator": [],
        "broker": list(broker or []),
        "shadow_runtime": [],
        "timeline": [],
        "telegram": [],
        "falcon": [],
        "external_exposure": list(external or []),
    }


@pytest.fixture(autouse=True)
def stable_validator(monkeypatch):
    monkeypatch.setattr(snapshot_module, "validate_trade_timeline", lambda *args, **kwargs: _timeline())


def test_not_found_is_successful_observational_result():
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(), now_epoch=BASE_TIME)
    assert result["ok"] is True
    assert result["snapshot_status"] == "NOT_FOUND"
    assert result["production_blocked"] is False


def test_healthy_open_trade_with_position_and_stop():
    opened = BASE_TIME - 600
    registry = _record(status="OPEN", opened_at=opened, qty=1.0, remaining_quantity=1.0, disaster_stop_confirmed=True)
    lifecycle = _record(state="POSITION_MANAGED", disaster_stop_confirmed=True)
    broker = _record(status="OPEN", position_found=True, contracts=1.0, mark_price=105.0)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "HEALTHY"
    assert result["trade_status"] == "OPEN"
    assert result["risk_protection"]["protection_status"] == "PROTECTED"


def test_healthy_closed_trade_does_not_require_broker_position():
    registry = _record(status="CLOSED", opened_at=BASE_TIME - 1000, closed_at=BASE_TIME - 10, remaining_quantity=0)
    lifecycle = _record(state="OUTCOME_RECORDED", event_type="OUTCOME_CONFIRMED")
    broker = _record(status="CLOSED", position_found=False, contracts=0)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "HEALTHY"
    assert result["trade_status"] == "CLOSED"


def test_broker_position_without_registry_is_divergent():
    broker = _record(status="OPEN", position_found=True, contracts=1)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(broker=[broker]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DIVERGENT"
    assert any(item["code"] == "BROKER_POSITION_WITHOUT_REGISTRY" for item in result["divergences"])


def test_open_without_broker_inside_grace_is_incomplete():
    registry = _record(status="OPEN", opened_at=BASE_TIME - 30, disaster_stop_confirmed=True)
    lifecycle = _record(state="ENTRY_PROTECTED", disaster_stop_confirmed=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "INCOMPLETE"
    assert any(item["code"] == "PENDING_WITHIN_GRACE_WINDOW" for item in result["warnings"])


def test_open_without_broker_after_grace_is_divergent():
    registry = _record(status="OPEN", opened_at=BASE_TIME - GRACE_WINDOWS["broker_ack_grace_seconds"] - 1, disaster_stop_confirmed=True)
    lifecycle = _record(state="ENTRY_PROTECTED", disaster_stop_confirmed=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DIVERGENT"


def test_lifecycle_closed_while_registry_open_is_divergent():
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600, disaster_stop_confirmed=True)
    lifecycle = _record(state="OUTCOME_RECORDED")
    broker = _record(status="OPEN", position_found=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker]), now_epoch=BASE_TIME)
    assert any(item["code"] == "LIFECYCLE_REGISTRY_STATE_CONFLICT" for item in result["divergences"])


def test_live_open_without_disaster_stop_is_critical_observation():
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600)
    lifecycle = _record(state="ENTRY_CONFIRMED")
    broker = _record(status="OPEN", position_found=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DIVERGENT"
    assert result["risk_protection"]["unprotected_position"] is True


@pytest.mark.parametrize("event,field", [("TP50_CONFIRMED", "tp50_confirmed"), ("BREAK_EVEN_CONFIRMED", "break_even_applied"), ("TRAILING_CONFIRMED", "trailing_active")])
def test_management_confirmations_are_trade_specific(event, field):
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600, disaster_stop_confirmed=True)
    lifecycle = _record(state="POSITION_MANAGED", event_type=event, disaster_stop_confirmed=True)
    broker = _record(status="OPEN", position_found=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker]), now_epoch=BASE_TIME)
    assert result["management"][field] is True


def test_multiple_trailing_updates_are_preserved():
    lifecycle = [_record(state="TRAILING_ACTIVE", event_type="TRAILING_CONFIRMED", event_id=f"T-{index}") for index in range(3)]
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600, disaster_stop_confirmed=True)
    broker = _record(status="OPEN", position_found=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=lifecycle, broker=[broker]), now_epoch=BASE_TIME)
    assert result["management"]["trailing_update_count"] == 3


def test_final_event_is_not_due_for_open_trade(monkeypatch):
    monkeypatch.setattr(snapshot_module, "validate_trade_timeline", lambda *args, **kwargs: _timeline("FAIL", missing=["LIVE_TRADE_CLOSED"]))
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600, disaster_stop_confirmed=True)
    lifecycle = _record(state="ENTRY_PROTECTED", disaster_stop_confirmed=True)
    broker = _record(status="OPEN", position_found=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker]), now_epoch=BASE_TIME)
    assert "LIVE_TRADE_CLOSED" in result["timeline_validation"]["not_due_events"]
    assert "LIVE_TRADE_CLOSED" not in result["timeline_validation"]["overdue_missing_events"]


def test_manual_position_same_symbol_remains_external():
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600, qty=1, disaster_stop_confirmed=True)
    lifecycle = _record(state="ENTRY_PROTECTED", disaster_stop_confirmed=True)
    broker = _record(status="OPEN", position_found=True, contracts=1)
    manual = {"external_position": True, "symbol": "BTCUSDT", "side": "LONG", "quantity": 9}
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[registry], lifecycle=[lifecycle], broker=[broker], external=[manual]), now_epoch=BASE_TIME)
    assert result["external_exposure"]["count"] == 1
    assert result["external_exposure"]["managed_by_central"] is False
    assert result["trade"]["original_quantity"] == 1


def test_other_bot_same_symbol_does_not_match():
    other = _record(trade_id="TR-DONKEY", lifecycle_id="LC-DONKEY", bot="DONKEY", status="OPEN", position_found=True)
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(registry=[other], broker=[other]), now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "NOT_FOUND"


def test_source_failure_is_degraded_and_fail_open():
    sources = _sources(registry=[_record(status="CLOSED")], lifecycle=[_record(state="OUTCOME_RECORDED")], broker=[_record(status="CLOSED", position_found=False)])
    sources["history_manager"] = lambda _: (_ for _ in ()).throw(OSError("private/path"))
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DEGRADED"
    assert result["fail_open"] is True and result["production_blocked"] is False
    assert "private/path" not in json.dumps(result)


def test_validator_exception_is_sanitized_and_fail_open(monkeypatch):
    monkeypatch.setattr(snapshot_module, "validate_trade_timeline", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret")))
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(), now_epoch=BASE_TIME)
    assert result["fail_open"] is True
    assert "secret" not in json.dumps(result)


def test_corrupt_reader_metadata_is_reported_without_raw_content():
    source = {"records": [_record(status="CLOSED")], "_reader_metadata": {"valid_lines": 1, "invalid_lines": 2, "partial": True}}
    sources = _sources(lifecycle=[_record(state="OUTCOME_RECORDED")], broker=[_record(status="CLOSED", position_found=False)])
    sources["registry"] = source
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert any(item["code"] == "CORRUPT_JSONL_LINES_SKIPPED" for item in result["warnings"])


def test_sources_are_collected_once_and_input_is_immutable():
    calls = {name: 0 for name in snapshot_module.SOURCE_ORDER}
    payload = [_record(status="CLOSED")]
    original = copy.deepcopy(payload)
    sources = {}
    for name in snapshot_module.SOURCE_ORDER:
        def source(_trade_id, component=name):
            calls[component] += 1
            return payload if component == "registry" else []
        sources[name] = source
    build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert all(value == 1 for value in calls.values())
    assert payload == original


def test_no_network_write_telegram_or_thread(monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    before_threads = {thread.ident for thread in threading.enumerate()}
    before_files = list(tmp_path.iterdir())
    result = build_live_trade_snapshot(TRADE_ID, sources=_sources(), now_epoch=BASE_TIME)
    assert result["ok"]
    assert {thread.ident for thread in threading.enumerate()} == before_threads
    assert list(tmp_path.iterdir()) == before_files == []


def test_response_is_json_serializable():
    json.dumps(build_live_trade_snapshot(TRADE_ID, sources=_sources(), now_epoch=BASE_TIME))


def test_invalid_input_returns_sanitized_error():
    result = build_live_trade_snapshot("../secret", sources=_sources())
    assert result["snapshot_status"] == "ERROR"
    assert "secret" not in json.dumps(result["errors"])
