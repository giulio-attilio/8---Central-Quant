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


def test_not_found_with_partial_history_preserves_coverage():
    sources = _sources()
    sources["history_manager"] = {
        "records": [],
        "_reader_metadata": {
            "valid_lines": 100,
            "invalid_lines": 0,
            "partial": True,
            "coverage_limited": True,
            "bytes_scanned": 1024,
        },
    }
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "NOT_FOUND"
    assert result["component_status"]["history_manager"]["status"] == "PARTIAL"
    assert result["coverage"]["history_manager"]["coverage_limited"] is True
    assert result["identity"]["matched_by"] == []


def test_not_found_with_fully_corrupt_timeline_preserves_degraded_source():
    sources = _sources()
    sources["timeline"] = {
        "records": [],
        "available": True,
        "_reader_metadata": {
            "valid_lines": 0,
            "invalid_lines": 3,
            "partial": True,
            "coverage_limited": True,
        },
    }
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "NOT_FOUND"
    assert result["component_status"]["timeline"]["status"] == "DEGRADED"
    assert any(item["code"] == "CORRUPT_JSONL_LINES_SKIPPED" for item in result["warnings"])
    assert result["identity"]["matched_by"] == []


def test_source_error_without_identity_is_degraded_not_internal_error():
    sources = _sources()
    sources["history_manager"] = lambda _: (_ for _ in ()).throw(PermissionError("denied"))
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DEGRADED"
    assert result["component_status"]["history_manager"]["status"] == "ERROR"
    assert result["identity"]["identity_confidence"] == "NONE"
    assert result["identity"]["matched_by"] == []
    assert result["fail_open"] is True


def test_any_proven_identifier_prevents_not_found_with_partial_history():
    sources = _sources(registry=[_record(status="CLOSED")], lifecycle=[_record(state="OUTCOME_RECORDED")], broker=[_record(status="CLOSED", position_found=False)])
    sources["history_manager"] = {
        "records": [],
        "_reader_metadata": {"valid_lines": 1, "partial": True, "coverage_limited": True},
    }
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DEGRADED"
    assert result["identity"]["identity_confidence"] == "HIGH"
    assert "trade_id" in result["identity"]["matched_by"]


def test_identified_trade_with_partially_corrupt_but_useful_timeline_is_degraded():
    sources = _sources(
        registry=[_record(status="CLOSED")],
        lifecycle=[_record(state="OUTCOME_RECORDED")],
        broker=[_record(status="CLOSED", position_found=False)],
    )
    sources["timeline"] = {
        "records": [_record(event_type="OUTCOME_CONFIRMED")],
        "_reader_metadata": {
            "valid_lines": 1,
            "invalid_lines": 2,
            "partial": True,
            "coverage_limited": True,
        },
    }
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DEGRADED"
    assert result["component_status"]["timeline"]["status"] == "PARTIAL"
    assert result["component_status"]["timeline"]["records"] == 1


def test_divergence_precedes_partial_source_for_identified_trade():
    registry = _record(status="OPEN", opened_at=BASE_TIME - 600)
    lifecycle = _record(state="ENTRY_CONFIRMED")
    broker = _record(status="OPEN", position_found=True)
    sources = _sources(registry=[registry], lifecycle=[lifecycle], broker=[broker])
    sources["history_manager"] = {
        "records": [],
        "_reader_metadata": {"valid_lines": 1, "partial": True, "coverage_limited": True},
    }
    result = build_live_trade_snapshot(TRADE_ID, sources=sources, now_epoch=BASE_TIME)
    assert result["snapshot_status"] == "DIVERGENT"
    assert result["risk_protection"]["unprotected_position"] is True


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


def _live_sol_registry(**updates):
    row = _record(
        trade_id="FALCON:FALCON15:SOLUSDT:SHORT",
        lifecycle_id="LC-SOL-LIVE",
        setup="FALCON15",
        symbol="SOLUSDT",
        side="SHORT",
        status="OPEN",
        opened_at=BASE_TIME - 600,
        qty=0.12,
        remaining_quantity=0.12,
        client_order_id="FALCON-LIVE-FALCON15-1784037618",
        broker_order_id="2077030442691940352",
        metadata={
            "broker_stop_order_id": "2077030444402577408",
            "partial_capable_sizing": {"market_limits": {"precision": {"amount": 0.01}, "amount_precision": 0.01}},
        },
    )
    row.update(updates)
    return row


def _live_sol_position():
    return {
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
        "symbol": "SOL/USDT:USDT",
        "position_side": "SHORT",
        "position_found": True,
        "position_status": "OPEN",
        "contracts": 0.12,
        "entry_price": 76.912,
    }


def _direct_stop(**updates):
    row = {
        "event": "BROKER_DISASTER_STOP_CREATED",
        "ok": True,
        "created": True,
        "status": "DISASTER_STOP_CREATED",
        "order_id": "2077030444402577408",
        "client_order_id": "FALCON-LIVE-FALCON15-178-DS",
        "symbol": "SOL-USDT",
        "side": "buy",
        "position_side": "SHORT",
        "amount": 0.12,
        "stop_price": 77.5585142857143,
    }
    row.update(updates)
    return row


def test_registry_authoritative_quantity_ignores_nested_precision_amount():
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), _direct_stop()]),
        now_epoch=BASE_TIME,
    )
    assert result["registry"]["initial_quantity"] == pytest.approx(0.12)
    assert result["registry"]["remaining_quantity"] == pytest.approx(0.12)
    assert result["broker"]["contracts"] == pytest.approx(0.12)
    assert not any(item.get("code") == "QUANTITY_CONFLICT" for item in result["divergences"])


def test_registry_initial_quantity_alias_precedes_secondary_root_quantity():
    registry = _live_sol_registry(metadata={"initial_quantity": 0.12}, quantity=0.01)
    registry.pop("remaining_quantity")
    registry.pop("qty")
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[registry], broker=[_live_sol_position(), _direct_stop()]),
        now_epoch=BASE_TIME,
    )
    assert result["registry"]["initial_quantity"] == pytest.approx(0.12)
    assert result["registry"]["remaining_quantity"] == pytest.approx(0.12)
    assert not any(item.get("code") == "QUANTITY_CONFLICT" for item in result["divergences"])
    assert result["broker"]["side"] == "SHORT"


def test_direct_broker_disaster_stop_is_recognized_as_physical_protection():
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), _direct_stop()]),
        now_epoch=BASE_TIME,
    )
    protection = result["risk_protection"]
    assert protection["disaster_stop_created"] is True
    assert protection["disaster_stop_confirmed"] is True
    assert protection["disaster_stop_order_id"] == "2077030444402577408"
    assert protection["disaster_stop_price"] == pytest.approx(77.5585142857143)
    assert protection["disaster_stop_quantity"] == pytest.approx(0.12)
    assert protection["protection_status"] == "PROTECTED"
    assert protection["unprotected_position"] is False
    assert not any(item.get("code") == "LIVE_POSITION_WITHOUT_DISASTER_STOP" for item in result["divergences"])


def test_exact_derived_ds_relation_links_strict_stop_after_main_identity_is_proven():
    registry = _live_sol_registry(metadata={})
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[registry], broker=[_live_sol_position(), _direct_stop()]),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is True
    assert result["risk_protection"]["disaster_stop_order_id"] == "2077030444402577408"


@pytest.mark.parametrize(
    "updates,expected_code",
    [
        ({"amount": None}, "STOP_PRICE_OR_QUANTITY_MISSING"),
        ({"stop_price": None}, "STOP_PRICE_OR_QUANTITY_MISSING"),
        ({"amount": 0.01}, "PROTECTED_QUANTITY_MISMATCH"),
    ],
)
def test_incomplete_or_mismatched_stop_never_suppresses_unprotected_warning(updates, expected_code):
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), _direct_stop(**updates)]),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["protection_status"] == "MISSING"
    codes = {item.get("code") for item in result["divergences"]}
    assert {"LIVE_POSITION_WITHOUT_DISASTER_STOP", expected_code}.issubset(codes)


def test_invalid_physical_stop_overrides_stale_local_confirmation_flags():
    registry = _live_sol_registry(disaster_stop_confirmed=True)
    lifecycle = _record(
        trade_id=registry["trade_id"], lifecycle_id="LC-SOL-LIVE", setup="FALCON15",
        symbol="SOLUSDT", side="SHORT", state="POSITION_MANAGED",
        disaster_stop_confirmed=True,
    )
    result = build_live_trade_snapshot(
        registry["trade_id"],
        sources=_sources(
            registry=[registry], lifecycle=[lifecycle],
            broker=[_live_sol_position(), _direct_stop(amount=0.01)],
        ),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["unprotected_position"] is True
    codes = {item.get("code") for item in result["divergences"]}
    assert {"PROTECTED_QUANTITY_MISMATCH", "LIVE_POSITION_WITHOUT_DISASTER_STOP"}.issubset(codes)


def test_newer_explicit_stop_failure_overrides_old_stop_and_stale_flags():
    registry = _live_sol_registry(disaster_stop_confirmed=True)
    lifecycle = _record(
        trade_id=registry["trade_id"], lifecycle_id="LC-SOL-LIVE", setup="FALCON15",
        symbol="SOLUSDT", side="SHORT", state="POSITION_MANAGED",
        disaster_stop_confirmed=True,
    )
    failed = {
        "event": "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "ok": False,
        "sent": True,
        "status": "LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "order_id": "2077030442691940352",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "symbol": "SOLUSDT",
        "position_side": "SHORT",
        "disaster_stop": {
            "ok": False,
            "created": False,
            "status": "DISASTER_STOP_ERROR",
            "error": "rejected",
        },
    }
    result = build_live_trade_snapshot(
        registry["trade_id"],
        sources=_sources(
            registry=[registry], lifecycle=[lifecycle],
            broker=[_live_sol_position(), _direct_stop(), failed],
        ),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["protection_status"] == "MISSING"
    codes = {item.get("code") for item in result["divergences"]}
    assert {"DISASTER_STOP_CREATION_FAILED", "LIVE_POSITION_WITHOUT_DISASTER_STOP"}.issubset(codes)


def test_direct_stop_error_is_linked_only_by_exact_derived_ds_relation():
    registry = _live_sol_registry(metadata={}, disaster_stop_confirmed=True)
    failed = {
        "event": "BROKER_DISASTER_STOP_ERROR",
        "ok": False,
        "created": False,
        "status": "DISASTER_STOP_ERROR",
        "client_order_id": "FALCON-LIVE-FALCON15-178-DS",
        "symbol": "SOLUSDT",
        "side": "buy",
        "position_side": "SHORT",
        "error": "rejected",
    }
    result = build_live_trade_snapshot(
        registry["trade_id"],
        sources=_sources(registry=[registry], broker=[_live_sol_position(), failed]),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert any(item.get("code") == "DISASTER_STOP_CREATION_FAILED" for item in result["divergences"])


def test_disaster_stop_with_wrong_closing_side_is_not_confirmed():
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(
            registry=[_live_sol_registry()],
            broker=[_live_sol_position(), _direct_stop(side="sell")],
        ),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["unprotected_position"] is True
    assert any(item.get("code") == "STOP_ACTION_SIDE_MISMATCH" for item in result["divergences"])


def test_stop_quantity_alias_never_replaces_main_broker_contracts():
    stop = _direct_stop()
    stop["quantity"] = 0.01
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), stop]),
        now_epoch=BASE_TIME,
    )
    assert result["broker"]["contracts"] == pytest.approx(0.12)
    assert not any(item.get("code") == "QUANTITY_CONFLICT" for item in result["divergences"])


def test_initial_send_amount_is_not_treated_as_current_contracts_after_partial_close():
    sent = {
        "event": "BROKER_LIVE_SENT", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "amount": 0.12, "symbol": "SOLUSDT", "position_side": "SHORT",
    }
    partial = {
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT", "event": "CLOSE_PARTIAL_RECORDED",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
    }
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(
            registry=[_live_sol_registry(remaining_quantity=0.06)],
            broker=[sent, partial, _direct_stop(amount=0.06)],
        ),
        now_epoch=BASE_TIME,
    )
    assert result["broker"]["contracts"] is None
    assert result["risk_protection"]["disaster_stop_confirmed"] is True
    assert result["risk_protection"]["disaster_stop_quantity"] == pytest.approx(0.06)
    assert not any(item.get("code") == "QUANTITY_CONFLICT" for item in result["divergences"])


def test_nested_disaster_stop_in_confirmed_broker_live_sent_is_recognized():
    broker = {
        "event": "BROKER_LIVE_SENT",
        "ok": True,
        "sent": True,
        "status": "SENT",
        "order_id": "2077030442691940352",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "symbol": "SOLUSDT",
        "position_side": "SHORT",
        "amount": 0.12,
        "disaster_stop": {
            "ok": True,
            "created": True,
            "status": "DISASTER_STOP_CREATED",
            "order_id": "2077030444402577408",
            "client_order_id": "FALCON-LIVE-FALCON15-178-DS",
            "amount": 0.12,
            "stop_price": 77.5585142857143,
        },
    }
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry()], broker=[broker]),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is True
    assert result["risk_protection"]["disaster_stop_order_id"] == "2077030444402577408"


def test_unrelated_ds_suffix_does_not_link_direct_stop_without_known_stop_order():
    registry = _live_sol_registry(metadata={})
    stop = _direct_stop(client_order_id="UNRELATED-CLIENT-DS")
    result = build_live_trade_snapshot(
        registry["trade_id"],
        sources=_sources(registry=[registry], broker=[_live_sol_position(), stop]),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["unprotected_position"] is True


def test_sent_order_with_failed_disaster_stop_is_acknowledged_but_unprotected(monkeypatch):
    from trade_timeline_validator import validate_trade_timeline as real_validator

    monkeypatch.setattr(snapshot_module, "validate_trade_timeline", real_validator)
    broker = {
        "event": "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "ok": False,
        "sent": True,
        "status": "LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "order_id": "2077030442691940352",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "symbol": "SOLUSDT",
        "position_side": "SHORT",
        "amount": 0.12,
        "disaster_stop": {"ok": False, "created": False, "error": "rejected"},
    }
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry()], broker=[broker]),
        now_epoch=BASE_TIME,
    )
    assert result["execution"]["order_sent"] is True
    assert result["execution"]["broker_acknowledged"] is True
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["unprotected_position"] is True


def test_stop_with_foreign_trade_identity_is_not_attributed():
    foreign_stop = _direct_stop(trade_id="TURTLE55:VETUSDT:LONG", bot="TURTLE", symbol="VETUSDT", position_side="LONG")
    result = build_live_trade_snapshot(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_sources(registry=[_live_sol_registry(metadata={})], broker=[_live_sol_position(), foreign_stop]),
        now_epoch=BASE_TIME,
    )
    assert result["risk_protection"]["disaster_stop_confirmed"] is False
    assert result["risk_protection"]["unprotected_position"] is True


def test_generic_shadow_match_status_does_not_claim_validated(monkeypatch):
    timeline = _timeline("FAIL", missing=["SHADOW_VALIDATED"])
    monkeypatch.setattr(snapshot_module, "validate_trade_timeline", lambda *args, **kwargs: timeline)
    sources = _sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), _direct_stop()])
    sources["shadow_runtime"] = [{
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "event_type": "TRADE_UPDATED",
        "status": "MATCH",
    }]
    result = build_live_trade_snapshot("FALCON:FALCON15:SOLUSDT:SHORT", sources=sources, now_epoch=BASE_TIME)
    assert result["shadow"]["observed"] is True
    assert result["shadow"]["matched"] is False


def test_snapshot_rejects_turtle_close_joined_only_by_ambiguous_ds_id():
    sources = _sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), _direct_stop()])
    sources["timeline"] = [{
        "trade_id": "TURTLE55:VETUSDT:LONG",
        "bot": "TURTLE",
        "symbol": "VETUSDT",
        "side": "LONG",
        "client_order_id": "FALCON-LIVE-FALCON15-178-DS",
        "event_type": "LIVE_TRADE_CLOSED",
        "timestamp": "2026-07-12T12:00:00Z",
    }]
    result = build_live_trade_snapshot("FALCON:FALCON15:SOLUSDT:SHORT", sources=sources, now_epoch=BASE_TIME)
    assert result["component_status"]["timeline"]["records"] == 0
    assert result["trade_status"] == "OPEN"


def test_current_live_trade_snapshot_is_protected_and_final_events_remain_not_due(monkeypatch):
    timeline = _timeline(
        "FAIL",
        missing=["LIVE_TRADE_CLOSED", "REGISTRY_CLOSE", "LIFECYCLE_FINISHED"],
    )
    timeline["events_found"] = [
        {"event": name}
        for name in ("SIGNAL_RECEIVED", "RISK_APPROVED", "EXECUTION_REQUESTED", "LIVE_ORDER_SENT", "BROKER_ACK", "POSITION_OPEN")
    ]
    monkeypatch.setattr(snapshot_module, "validate_trade_timeline", lambda *args, **kwargs: timeline)
    sources = _sources(registry=[_live_sol_registry()], broker=[_live_sol_position(), _direct_stop()])
    result = build_live_trade_snapshot("FALCON:FALCON15:SOLUSDT:SHORT", sources=sources, now_epoch=BASE_TIME)
    assert result["risk_protection"]["protection_status"] == "PROTECTED"
    assert not any(item.get("code") in {"QUANTITY_CONFLICT", "LIVE_POSITION_WITHOUT_DISASTER_STOP"} for item in result["divergences"])
    assert set(result["timeline_validation"]["not_due_events"]) == {"LIVE_TRADE_CLOSED", "REGISTRY_CLOSE", "LIFECYCLE_FINISHED"}
    assert result["timeline_validation"]["overdue_missing_events"] == []
    assert result["execution"]["execution_requested"] is True
    assert result["execution"]["order_sent"] is True
    assert result["execution"]["broker_acknowledged"] is True
    json.dumps(result)
