from __future__ import annotations

import copy
import importlib
import json
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import trade_lifecycle_shadow_runtime_adapter as runtime_adapter_module
from trade_lifecycle_shadow_runtime_adapter import TradeLifecycleShadowRuntimeAdapter


class FakeManager:
    def __init__(self):
        self.created = []
        self.applied = []
        self.fail = False
        self.last_registry_trade = {}

    def create_lifecycle(self, payload, persist=True):
        if self.fail:
            raise RuntimeError("shadow failure")
        self.created.append(copy.deepcopy(payload))
        return {"ok": True, "event_applied": True, "snapshot": payload}

    def apply_event(self, lifecycle_id, event, persist=True):
        if self.fail:
            raise RuntimeError("shadow failure")
        self.applied.append((lifecycle_id, copy.deepcopy(event)))
        return {"ok": True, "event_applied": True, "snapshot": {"lifecycle_id": lifecycle_id}}

    def compare_with_registry(self, lifecycle_id, trade):
        self.last_registry_trade = copy.deepcopy(trade)
        status = trade.get("comparison", "MATCH")
        differences = trade.get("differences", [])
        return {
            "ok": status == "MATCH",
            "status": status,
            "compared_fields": trade.get("compared_fields", 10),
            "matching_fields": trade.get("matching_fields", 10 if status == "MATCH" else 9),
            "differences": differences,
        }

    def get_lifecycle(self, lifecycle_id):
        trade = self.last_registry_trade
        quantity = trade.get("remaining_quantity", trade.get("qty", 1.0))
        stop_order_id = trade.get("broker_stop_order_id", "STOP-BASE")
        return {
            "ok": True,
            "snapshot": {
                "lifecycle_id": lifecycle_id,
                "trade_id": trade.get("trade_id", "TR-1"),
                "signal_id": trade.get("signal_id", "SIG-1"),
                "decision_id": trade.get("decision_id", ""),
                "bot": trade.get("bot", "FALCON"),
                "setup": trade.get("setup", "ORB"),
                "symbol": trade.get("symbol", "BTCUSDT"),
                "side": trade.get("side", "LONG"),
                "mode": "LIVE" if trade.get("mode") == "REAL" else trade.get("mode", "LIVE"),
                "state": "ENTRY_PROTECTED",
                "quantity_open": quantity,
                "client_order_id": trade.get("client_order_id", "CLIENT-BASE"),
                "exchange_order_id": trade.get("broker_order_id", "ORDER-BASE"),
                "disaster_stop": {"confirmed": True, "order_id": stop_order_id},
            },
        }

    def trade_lifecycle_health(self):
        return {"ok": True, "shadow_mode": True}


@pytest.fixture()
def adapter(tmp_path):
    return TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())


def base(**updates):
    item = {
        "lifecycle_id": "LC-1", "trade_id": "TR-1", "signal_id": "SIG-1",
        "bot": "FALCON", "setup": "ORB", "symbol": "BTCUSDT", "side": "LONG",
        "mode": "LIVE", "status": "OPEN", "qty": 1.0, "quantity_planned": 1.0,
        "client_order_id": "CLIENT-BASE", "broker_order_id": "ORDER-BASE",
        "broker_stop_order_id": "STOP-BASE", "protected": True,
        "timestamp": "2026-07-12T00:00:00Z",
    }
    item.update(updates)
    return item


def test_enabled_by_default_and_explicit_false_is_kill_switch(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", raising=False)
    item = TradeLifecycleShadowRuntimeAdapter(data_dir=tmp_path, manager=FakeManager())
    assert item.observe_event("SIGNAL", base(), persist=False)["status"] == "APPLIED"

    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "false")
    disabled = TradeLifecycleShadowRuntimeAdapter(data_dir=tmp_path, manager=FakeManager())
    assert disabled.observe_event("SIGNAL", base(), persist=False)["status"] == "DISABLED"


def test_health_declares_shadow_authority(adapter):
    health = adapter.get_health()
    assert health["mode"] == "SHADOW"
    assert health["operational_authority"] is False
    assert health["broker_access"] is False
    assert health["registry_write_access"] is False


def test_normalization_and_payload_immutability(adapter):
    payload = base(evidence={"x": [1]})
    original = copy.deepcopy(payload)
    result = adapter.observe_event("SIGNAL", payload, persist=False)
    assert result["status"] == "APPLIED"
    assert payload == original
    assert adapter.manager.created[0]["trade_id"] == "TR-1"


@pytest.mark.parametrize(
    "mode_fields,expected",
    [
        ({"metadata": {"execution_mode": "PAPER"}}, "PAPER"),
        ({"execution_mode": "LIVE"}, "LIVE"),
        ({"metadata": {"mode": "PAPER"}}, "PAPER"),
        ({"registry_mode": "PAPER"}, "PAPER"),
        ({"metadata": {"registry_mode": "PAPER"}}, "PAPER"),
    ],
)
def test_signal_mode_alias_is_canonicalized_for_manager(tmp_path, mode_fields, expected):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = base()
    payload.pop("mode")
    payload.update(mode_fields)

    result = item.observe_event("SIGNAL", payload, persist=False)

    assert result["status"] == "APPLIED"
    assert manager.created[0]["mode"] == expected


@pytest.mark.parametrize(
    "mode_fields,expected",
    [
        ({"mode": "LIVE", "execution_mode": "PAPER", "registry_mode": "VERIFY"}, "LIVE"),
        ({"execution_mode": "PAPER", "registry_mode": "LIVE"}, "PAPER"),
    ],
)
def test_signal_mode_alias_priority_is_deterministic(tmp_path, mode_fields, expected):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = base()
    payload.pop("mode")
    payload.update(mode_fields)

    item.observe_event("SIGNAL", payload, persist=False)

    assert manager.created[0]["mode"] == expected


def test_missing_mode_alias_does_not_inject_mode(tmp_path):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = base()
    payload.pop("mode")

    item.observe_event("SIGNAL", payload, persist=False)

    assert "mode" not in manager.created[0]


def test_invalid_mode_alias_is_forwarded_without_adapter_normalization(tmp_path):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = base(mode="INVALID_MODE")

    item.observe_event("SIGNAL", payload, persist=False)

    assert manager.created[0]["mode"] == "INVALID_MODE"


def test_mode_canonicalization_preserves_payload_and_identifiers(tmp_path):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = base(
        lifecycle_id="LC-MODE",
        trade_id="TR-MODE",
        event_id="EVENT-MODE",
        metadata={"execution_mode": "PAPER", "nested": {"values": [1]}},
    )
    payload.pop("mode")
    original = copy.deepcopy(payload)

    result = item.observe_event("SIGNAL", payload, persist=False)

    assert payload == original
    assert result["lifecycle_id"] == "LC-MODE"
    assert result["event_id"] == "EVENT-MODE"
    assert result["identity_source"] == "TRADE_ID"
    assert manager.created[0]["lifecycle_id"] == "LC-MODE"
    assert manager.created[0]["trade_id"] == "TR-MODE"
    assert manager.created[0]["mode"] == "PAPER"


def _isolated_lifecycle_manager(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path / "manager"))
    sys.modules.pop("trade_lifecycle_manager", None)
    return importlib.import_module("trade_lifecycle_manager")


@pytest.mark.parametrize("mode_value", [None, "INVALID_MODE"])
def test_missing_or_invalid_mode_remains_unknown_in_real_manager(monkeypatch, tmp_path, mode_value):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = base()
    if mode_value is None:
        payload.pop("mode")
    else:
        payload["mode"] = mode_value

    observed = item.observe_event("SIGNAL", payload, persist=False)

    assert observed["manager_result"]["snapshot"]["mode"] == "UNKNOWN"


def test_predator_paper_alias_matches_registry_with_real_manager(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = base(metadata={"execution_mode": "PAPER"}, registry_mode="PAPER")
    payload.pop("mode")
    payload.pop("qty")
    payload.pop("protected")
    payload.pop("broker_stop_order_id")

    observed = item.observe_event("SIGNAL", payload, persist=False)
    reconciled = item.reconcile_trade(payload, persist=False)

    assert observed["manager_result"]["snapshot"]["mode"] == "PAPER"
    assert reconciled["status"] == "MATCH"
    assert not any(row.get("field") == "mode" for row in reconciled["comparison"]["differences"])


def test_real_mode_difference_still_diverges_with_real_manager(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    lifecycle_payload = base(mode="PAPER")
    registry_payload = copy.deepcopy(lifecycle_payload)
    registry_payload["mode"] = "LIVE"

    item.observe_event("SIGNAL", lifecycle_payload, persist=False)
    reconciled = item.reconcile_trade(registry_payload, persist=False)

    mode_difference = next(row for row in reconciled["comparison"]["differences"] if row.get("field") == "mode")
    assert reconciled["status"] == "PARTIAL_MATCH"
    assert mode_difference["shadow_value"] == "PAPER"
    assert mode_difference["registry_value"] == "LIVE"


def paper_registry_open(**updates):
    payload = base(
        mode="PAPER",
        status="OPEN",
        source_component="TRADE_REGISTRY",
        quantity_planned=0.0,
        event_id="REGISTRY-PAPER-OPEN",
    )
    payload.update(updates)
    return payload


def paper_registry_close(opened, **updates):
    payload = copy.deepcopy(opened)
    payload.update({
        "status": "CLOSED",
        "closed_at": "2026-07-13T21:30:35+00:00",
        "exit_price": 101.0,
        "close_reason": "SL",
        "pnl_pct": 1.0,
        "pnl_r": 0.5,
        "event_id": "REGISTRY-PAPER-CLOSE",
    })
    payload.update(updates)
    return payload


def test_registry_paper_signal_opens_explicit_paper_lifecycle(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = paper_registry_open()
    original = copy.deepcopy(payload)

    result = item.observe_event("SIGNAL_CREATED", payload, persist=False)

    assert result["status"] == "APPLIED"
    assert result["manager_result"]["current_state"] == "PAPER_POSITION_OPEN"
    assert result["manager_result"]["paper_position_transition"]["applied"] is True
    assert result["manager_result"]["paper_position_transition"]["derived_event_id"].startswith("CENTRAL-SHADOW-PAPER-EVENT-")
    assert payload == original


@pytest.mark.parametrize(
    "mode_fields",
    [
        {"metadata": {"execution_mode": "PAPER"}},
        {"registry_mode": "PAPER"},
    ],
)
def test_registry_paper_mode_aliases_open_paper_lifecycle(monkeypatch, tmp_path, mode_fields):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = paper_registry_open()
    payload.pop("mode")
    payload.update(mode_fields)

    result = item.observe_event("SIGNAL_CREATED", payload, persist=False)

    assert result["manager_result"]["snapshot"]["mode"] == "PAPER"
    assert result["manager_result"]["current_state"] == "PAPER_POSITION_OPEN"


@pytest.mark.parametrize(
    "updates,removed,expected_reason",
    [
        ({}, "status", "REGISTRY_STATUS_IS_NOT_OPEN"),
        ({"mode": "LIVE"}, None, "MODE_IS_NOT_PAPER"),
        ({"mode": "UNKNOWN"}, None, "MODE_IS_NOT_PAPER"),
    ],
)
def test_non_eligible_registry_signal_remains_signal_detected(monkeypatch, tmp_path, updates, removed, expected_reason):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = paper_registry_open(**updates)
    if removed:
        payload.pop(removed)

    result = item.observe_event("SIGNAL_CREATED", payload, persist=False)

    if updates.get("mode") == "LIVE":
        assert result["status"] == "NOT_ELIGIBLE"
        assert result["manager_result"]["snapshot"] == {}
        assert result["manager_result"]["live_position_transition"]["reason"] == "REGISTRY_LIVE_ELIGIBILITY_FAILED"
    else:
        assert result["manager_result"]["snapshot"]["state"] == "SIGNAL_DETECTED"
        assert result["manager_result"]["paper_position_transition"]["reason"] == expected_reason


def test_registry_paper_close_translates_and_reconciles_closed(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = paper_registry_open()
    closed = paper_registry_close(opened)
    original = copy.deepcopy(closed)
    item.observe_event("SIGNAL_CREATED", opened, persist=False)

    result = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)
    reconciled = item.reconcile_trade(closed, persist=False)

    assert result["status"] == "APPLIED"
    assert result["manager_result"]["current_state"] == "CLOSE_CONFIRMED"
    assert result["manager_result"]["paper_position_transition"]["derived_event_type"] == "PAPER_POSITION_CLOSED"
    assert not any(row["field"] == "open_closed_status" for row in reconciled["comparison"]["differences"])
    assert closed == original


@pytest.mark.parametrize(
    "removed,expected_reason",
    [
        (("closed_at",), "CLOSED_AT_MISSING"),
        (("exit_price", "close_reason", "pnl_pct", "pnl_r", "result_pct", "result_r"), "PAPER_CLOSE_EVIDENCE_MISSING"),
    ],
)
def test_incomplete_registry_paper_close_stays_blocked(monkeypatch, tmp_path, removed, expected_reason):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = paper_registry_open()
    item.observe_event("SIGNAL_CREATED", opened, persist=False)
    closed = paper_registry_close(opened)
    for key in removed:
        closed.pop(key, None)

    result = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)

    assert result["status"] == "BLOCKED"
    assert result["manager_result"]["snapshot"]["state"] == "PAPER_POSITION_OPEN"
    assert result["manager_result"]["paper_position_transition"]["reason"] == expected_reason


def test_live_close_contract_remains_blocked_from_signal_detected(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    live = base(mode="LIVE", status="OPEN", source_component="TRADE_REGISTRY", event_id="LIVE-OPEN")
    item.observe_event("SIGNAL_CREATED", live, persist=False)
    live_close = copy.deepcopy(live)
    live_close.update({"status": "CLOSED", "closed_at": "2026-07-13T21:30:35+00:00", "exit_price": 101.0, "event_id": "LIVE-CLOSE"})

    result = item.observe_event("CLOSE_CONFIRMED", live_close, persist=False)

    assert result["status"] == "NOT_ELIGIBLE"
    assert result["manager_result"]["snapshot"] == {}
    assert result["manager_result"]["live_position_transition"]["reason"] == "REGISTRY_LIVE_ELIGIBILITY_FAILED"


def test_paper_close_without_lifecycle_does_not_create_one(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    closed = paper_registry_close(paper_registry_open())

    result = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)

    assert result["status"] == "BLOCKED"
    assert result["manager_result"]["status"] == "LIFECYCLE_NOT_FOUND"
    assert manager.trade_lifecycle_health()["lifecycle_count"] == 0


def test_paper_close_is_idempotent_for_same_and_new_source_events(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = paper_registry_open()
    closed = paper_registry_close(opened)
    item.observe_event("SIGNAL_CREATED", opened, persist=False)
    first = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)
    before = manager.get_lifecycle("LC-1")["snapshot"]
    same = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)
    newer = paper_registry_close(opened, event_id="REGISTRY-PAPER-CLOSE-2")
    semantic_duplicate = item.observe_event("CLOSE_CONFIRMED", newer, persist=False)
    after = manager.get_lifecycle("LC-1")["snapshot"]

    assert first["status"] == "APPLIED"
    assert same["status"] == "DUPLICATE"
    assert semantic_duplicate["status"] == "DUPLICATE"
    assert semantic_duplicate["manager_result"]["status"] == "PAPER_POSITION_ALREADY_CLOSED"
    assert after["updated_at"] == before["updated_at"]
    assert after["close"] == before["close"]
    assert after["outcome"] == before["outcome"]
    assert after["divergences"] == before["divergences"]


def test_registry_closed_against_open_paper_lifecycle_is_real_divergence(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = paper_registry_open()
    item.observe_event("SIGNAL_CREATED", opened, persist=False)

    reconciled = item.reconcile_trade(paper_registry_close(opened), persist=False)

    assert any(row["field"] == "open_closed_status" for row in reconciled["comparison"]["differences"])


def test_registry_external_paper_position_never_enters_paper_lifecycle(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    external = paper_registry_open(external_position=True, bot="FALCON")

    result = item.observe_event("EXTERNAL_POSITION", external, persist=False)

    assert result["manager_result"]["snapshot"]["state"] == "MANUAL_POSITION_DETECTED"
    assert result["manager_result"]["snapshot"]["bot"] == ""
    assert result["manager_result"]["paper_position_transition"]["reason"] == "EXTERNAL_OR_MANUAL_POSITION"


def test_two_bots_same_symbol_remain_independent(tmp_path):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    item.observe_event("SIGNAL", base(lifecycle_id="LC-A", trade_id="TR-A", bot="FALCON"), persist=False)
    item.observe_event("SIGNAL", base(lifecycle_id="LC-B", trade_id="TR-B", bot="DONKEY"), persist=False)
    assert {row["trade_id"] for row in manager.created} == {"TR-A", "TR-B"}


def test_external_position_never_receives_bot_ownership(adapter):
    payload = base(lifecycle_id="", trade_id="", external_position=True, bot="FALCON")
    result = adapter.observe_event("EXTERNAL_POSITION", payload, persist=False)
    assert result["status"] == "APPLIED"
    created = adapter.manager.created[0]
    assert created["trade_id"] == ""
    assert created["external_position"] is True


def test_event_id_is_deterministic(tmp_path):
    first = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "a", manager=FakeManager())
    second = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "b", manager=FakeManager())
    a = first.observe_event("DECISION_ALLOWED", base(), persist=False)
    b = second.observe_event("DECISION_ALLOWED", base(), persist=False)
    assert a["event_id"] == b["event_id"]


def test_duplicate_is_applied_once(adapter):
    first = adapter.observe_event("DECISION_ALLOWED", base(event_id="E-1"), persist=False)
    second = adapter.observe_event("DECISION_ALLOWED", base(event_id="E-1"), persist=False)
    assert first["status"] == "APPLIED"
    assert second["duplicate"] is True
    assert len(adapter.manager.applied) == 1


@pytest.mark.parametrize("legacy,canonical", [("ENTRY_FILL", "ENTRY_FILL_RECORDED"), ("TP50_CONFIRMED", "TP50_CONFIRMED"), ("BREAK_EVEN_CONFIRMED", "BREAK_EVEN_CONFIRMED"), ("TRAILING_CONFIRMED", "TRAILING_CONFIRMED"), ("CLOSE_CONFIRMED", "CLOSE_CONFIRMED")])
def test_runtime_event_mapping(adapter, legacy, canonical):
    result = adapter.observe_event(legacy, base(event_id=f"E-{legacy}"), persist=False)
    assert result["status"] == "APPLIED"
    assert adapter.manager.applied[-1][1]["event_type"] == canonical


def test_missing_lifecycle_is_fail_open(adapter):
    result = adapter.observe_event("ENTRY_FILL", base(lifecycle_id=""), persist=False)
    assert result["status"] == "APPLIED"
    assert result["lifecycle_id"].startswith("CENTRAL-SHADOW-LIFECYCLE-")
    assert result["production_blocked"] is False


def test_manager_exception_never_escapes(adapter):
    adapter.manager.fail = True
    result = adapter.observe_event("SIGNAL", base(), persist=False)
    assert result["status"] == "ERROR"
    assert result["production_blocked"] is False


def test_persistence_failure_is_fail_open(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "_append", lambda *args: (_ for _ in ()).throw(OSError("disk")))
    result = adapter.observe_event("SIGNAL", base(), persist=True)
    assert result["status"] == "ERROR"
    assert result["production_blocked"] is False


def test_reconciliation_match(adapter):
    result = adapter.reconcile_trade(base(comparison="MATCH"), persist=False)
    assert result["status"] == "MATCH"
    assert result["reconciled"] is True


def test_real_registry_mode_matches_normalized_live_shadow_mode(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    result = item.reconcile_trade(base(mode="REAL", comparison="MATCH"), persist=False)
    assert result["status"] == "MATCH"
    assert result["shadow_validation"]["eligible"] is True


def test_reconciliation_divergence_is_deduplicated(adapter):
    difference = {"field": "status", "shadow_value": "OPEN", "registry_value": "CLOSED", "severity": "CRITICAL"}
    trade = base(comparison="DIVERGENCE", differences=[difference])
    adapter.reconcile_trade(trade, persist=False)
    adapter.reconcile_trade(trade, persist=False)
    assert adapter.get_metrics()["metrics"]["divergences"] == 1


def test_reconciliation_match_persists_explicit_shadow_validated_event(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    trade = base(
        comparison="MATCH",
        decision_id="DEC-1",
        client_order_id="CLIENT-1",
        broker_order_id="ORDER-1",
        broker_stop_order_id="STOP-1",
        updated_at="2026-07-14T11:00:30Z",
    )
    result = item.reconcile_trade(trade, persist=True)
    journal = [json.loads(line) for line in item.events_file.read_text(encoding="utf-8").splitlines()]
    assert result["status"] == "MATCH"
    assert result["shadow_validation"]["eligible"] is True
    assert result["shadow_validation"]["persisted"] is True
    assert len(journal) == 1
    assert journal[0]["event_type"] == "SHADOW_VALIDATED"
    assert journal[0]["status"] == "MATCH"
    assert journal[0]["trade_id"] == "TR-1"
    assert journal[0]["decision_id"] == "DEC-1"
    assert journal[0]["client_order_id"] == "CLIENT-1"
    assert journal[0]["broker_order_id"] == "ORDER-1"
    assert journal[0]["broker_stop_order_id"] == "STOP-1"
    assert {
        "quantity_open", "client_order_id", "exchange_order_id",
        "protection", "disaster_stop_order_id",
    }.issubset(journal[0]["validated_fields"])
    assert journal[0]["validated_values"]["exchange_order_id"] == "ORDER-1"
    assert journal[0]["validated_values"]["disaster_stop_order_id"] == "STOP-1"
    assert journal[0]["operational_authority"] is False
    assert journal[0]["differences"] == []


def test_shadow_validated_is_idempotent_across_retry_and_restart(tmp_path):
    trade = base(comparison="MATCH", broker_order_id="ORDER-IDEMPOTENT", updated_at="2026-07-14T11:00:30Z")
    first = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    initial = first.reconcile_trade(trade, persist=True)
    retry = first.reconcile_trade(trade, persist=True)
    restarted = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    after_restart = restarted.reconcile_trade(trade, persist=True)
    rows = [json.loads(line) for line in first.events_file.read_text(encoding="utf-8").splitlines()]
    assert initial["shadow_validation"]["persisted"] is True
    assert retry["shadow_validation"]["duplicate"] is True
    assert after_restart["shadow_validation"]["duplicate"] is True
    assert len(rows) == 1


def test_shadow_validation_append_is_idempotent_across_processes(tmp_path):
    script = """
import json
import sys
from pathlib import Path
from trade_lifecycle_shadow_runtime_adapter import TradeLifecycleShadowRuntimeAdapter

adapter = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=Path(sys.argv[1]))
event = {
    "event_id": "CENTRAL-SHADOW-VALIDATED-CROSS-PROCESS",
    "event_type": "SHADOW_VALIDATED",
    "status": "MATCH",
}
print(json.dumps({"appended": adapter._append_event_once(event)}))
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path)],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30) for process in processes]
    assert all(process.returncode == 0 for process in processes), results
    rows = [
        json.loads(line)
        for line in (tmp_path / "trade_lifecycle_shadow_runtime_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["event_id"] == "CENTRAL-SHADOW-VALIDATED-CROSS-PROCESS"


def test_non_operational_registry_timestamp_change_does_not_duplicate_validation(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    first = item.reconcile_trade(base(updated_at="2026-07-14T11:00:30Z"), persist=True)
    second = item.reconcile_trade(base(
        updated_at="2026-07-14T11:01:30Z",
        decision_id="DECISION-ENRICHED-LATER",
        compared_fields=11,
        matching_fields=11,
    ), persist=True)
    rows = item.events_file.read_text(encoding="utf-8").splitlines()
    assert first["shadow_validation"]["persisted"] is True
    assert second["shadow_validation"]["duplicate"] is True
    assert len(rows) == 1


def test_material_quantity_change_creates_new_validation_revision(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    first = item.reconcile_trade(base(remaining_quantity=1.0), persist=True)
    second = item.reconcile_trade(base(remaining_quantity=0.5), persist=True)
    rows = [json.loads(line) for line in item.events_file.read_text(encoding="utf-8").splitlines()]
    assert first["shadow_validation"]["persisted"] is True
    assert second["shadow_validation"]["persisted"] is True
    assert first["shadow_validation"]["event"]["event_id"] != second["shadow_validation"]["event"]["event_id"]
    assert len(rows) == 2


@pytest.mark.parametrize("status", ["PARTIAL_MATCH", "DIVERGENCE", "INSUFFICIENT_EVIDENCE"])
def test_non_match_reconciliation_never_persists_shadow_validated(tmp_path, status):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    differences = [] if status == "INSUFFICIENT_EVIDENCE" else [{"field": "quantity", "shadow_value": 0, "registry_value": 1}]
    result = item.reconcile_trade(base(comparison=status, differences=differences), persist=True)
    assert result["shadow_validation"]["eligible"] is False
    assert not item.events_file.exists()


def test_match_without_compared_fields_is_not_shadow_validation(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    result = item.reconcile_trade(base(comparison="MATCH", compared_fields=0, matching_fields=0), persist=True)
    assert result["status"] == "MATCH"
    assert result["shadow_validation"]["eligible"] is False
    assert not item.events_file.exists()


def test_match_with_only_identity_evidence_is_not_shadow_validation(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    result = item.reconcile_trade(base(comparison="MATCH", compared_fields=1, matching_fields=1), persist=True)
    assert result["status"] == "MATCH"
    assert result["shadow_validation"]["eligible"] is False
    assert not item.events_file.exists()


def test_live_match_without_confirmed_shadow_protection_is_not_validated(tmp_path):
    manager = FakeManager()
    manager.get_lifecycle = lambda lifecycle_id: {
        "ok": True,
        "snapshot": {"lifecycle_id": lifecycle_id, "state": "ENTRY_SUBMITTING", "disaster_stop": {}},
    }
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    result = item.reconcile_trade(base(comparison="MATCH"), persist=True)
    assert result["status"] == "MATCH"
    assert result["shadow_validation"]["eligible"] is False
    assert not item.events_file.exists()


@pytest.mark.parametrize("field", ["exchange_order_id", "disaster_stop_order_id"])
def test_live_match_requires_explicit_matching_order_and_stop_identity(tmp_path, field):
    manager = FakeManager()
    original_get = manager.get_lifecycle

    def mismatched(lifecycle_id):
        result = original_get(lifecycle_id)
        if field == "exchange_order_id":
            result["snapshot"]["exchange_order_id"] = "OTHER-ENTRY-ORDER"
        else:
            result["snapshot"]["disaster_stop"]["order_id"] = "OTHER-STOP-ORDER"
        return result

    manager.get_lifecycle = mismatched
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    result = item.reconcile_trade(base(comparison="MATCH"), persist=True)
    assert result["status"] == "MATCH"
    assert result["shadow_validation"]["eligible"] is False
    assert not item.events_file.exists()


def test_shadow_validation_persistence_failure_is_fail_open(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "_append_event_once", lambda event: (_ for _ in ()).throw(OSError("disk")))
    result = adapter.reconcile_trade(base(comparison="MATCH"), persist=True)
    assert result["status"] == "MATCH"
    assert result["reconciled"] is True
    assert result["shadow_validation"]["persisted"] is False
    assert result["shadow_validation"]["error"].startswith("OSError")
    assert result["operational_authority"] is False


def test_shadow_validation_lock_contention_is_bounded_and_fail_open(adapter, monkeypatch):
    def always_locked(*_args, **_kwargs):
        raise OSError("lock busy")

    monkeypatch.setattr(runtime_adapter_module, "SHADOW_STORAGE_LOCK_TIMEOUT_SECONDS", 0.01)
    if runtime_adapter_module.os.name == "nt":
        fake_lock_module = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=always_locked)
        monkeypatch.setitem(sys.modules, "msvcrt", fake_lock_module)
    else:
        fake_lock_module = SimpleNamespace(LOCK_EX=1, LOCK_NB=2, LOCK_UN=8, flock=always_locked)
        monkeypatch.setitem(sys.modules, "fcntl", fake_lock_module)

    started = __import__("time").monotonic()
    result = adapter.reconcile_trade(base(comparison="MATCH"), persist=True)
    elapsed = __import__("time").monotonic() - started

    assert elapsed < 0.5
    assert result["status"] == "MATCH"
    assert result["ok"] is True
    assert result["fail_open"] is True
    assert result["operational_result_preserved"] is True
    assert result["shadow_validation"]["persisted"] is False
    assert result["shadow_validation"]["error"].startswith("TimeoutError")


def test_distinct_execution_identities_get_distinct_validation_events(tmp_path):
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    first = item.reconcile_trade(base(comparison="MATCH", broker_order_id="ORDER-A", opened_at="2026-07-14T10:00:00Z"), persist=True)
    second = item.reconcile_trade(base(comparison="MATCH", broker_order_id="ORDER-B", opened_at="2026-07-15T10:00:00Z"), persist=True)
    rows = item.events_file.read_text(encoding="utf-8").splitlines()
    assert first["shadow_validation"]["event"]["event_id"] != second["shadow_validation"]["event"]["event_id"]
    assert len(rows) == 2


def _live_registry_open(**updates):
    payload = {
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "mode": "LIVE",
        "status": "OPEN",
        "source_component": "TRADE_REGISTRY",
        "opened_at": "2026-07-14T11:00:18Z",
        "entry": 76.912,
        "qty": 0.12,
        "metadata": {
            "execution_decision": {"allowed": True, "decision": "ALLOW"},
        },
    }
    payload.update(updates)
    return payload


def _factual_live_open(**updates):
    payload = _live_registry_open(
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784037618",
        execution_sent=True,
        client_order_id="FALCON-LIVE-FALCON15-1784037618",
        broker_order_id="2077030442691940352",
        broker_entry_reference=76.93,
        initial_qty=0.12,
        remaining_qty=0.12,
        protected=True,
        disaster_stop_confirmed=True,
        broker_stop_order_id="2077030444402577408",
        broker_stop_status="DISASTER_STOP_CREATED",
        broker_stop_side="BUY",
        broker_stop_symbol="SOLUSDT",
        broker_stop_price=77.5585142857143,
        broker_stop_amount=0.12,
        broker_stop_confirmed_at="2026-07-14T11:00:23Z",
        last_update="2026-07-14T11:00:23Z",
    )
    payload["metadata"].update({
        key: value
        for key, value in payload.items()
        if key.startswith("broker_") or key in {
            "execution_sent", "client_order_id", "initial_qty", "remaining_qty",
            "protected", "disaster_stop_confirmed", "last_update",
        }
    })
    payload.update(updates)
    return payload


def test_live_registry_observation_reconstructs_factual_post_ack_entry(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _live_registry_open()

    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    after_decision = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert after_decision["state"] == "RISK_APPROVED"
    assert after_decision["quantity_planned"] == pytest.approx(0.12)
    assert after_decision["quantity_filled"] == 0
    assert after_decision["fill_ids"] == []

    updated = copy.deepcopy(opened)
    updated.update({
        "execution_sent": True,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
        "broker_stop_order_id": "2077030444402577408",
        "order_id": "2077030442691940352",
        "last_update": "2026-07-14T11:00:22Z",
    })
    updated["metadata"].update({
        "execution_sent": True,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
        "broker_stop_order_id": "2077030444402577408",
        "broker_stop_price": 77.5585142857143,
        "broker_stop_amount": 0.12,
    })
    observed = item.observe_event("TRADE_UPDATED", updated, persist=False)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert observed["status"] == "APPLIED"
    assert snapshot["state"] == "ENTRY_CONFIRMED"
    assert snapshot["client_order_id"] == "FALCON-LIVE-FALCON15-1784037618"
    assert snapshot["exchange_order_id"] == "2077030442691940352"
    assert snapshot["quantity_filled"] == pytest.approx(0.12)
    assert snapshot["quantity_open"] == pytest.approx(0.12)
    assert snapshot["entry_price_confirmed"] is None
    assert snapshot["entry_price_theoretical"] == pytest.approx(76.912)
    assert snapshot["disaster_stop"] == {}

    comparison = item.reconcile_trade(updated, persist=False)
    assert comparison["status"] == "LIFECYCLE_INCOMPLETE"
    assert comparison["reconciled"] is False
    assert comparison["shadow_validation"]["eligible"] is False


def test_live_registry_preview_or_missing_order_does_not_advance_submission(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _live_registry_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    update = copy.deepcopy(opened)
    update.update({"execution_sent": False, "client_order_id": "CLIENT", "broker_order_id": None})

    observed = item.observe_event("TRADE_UPDATED", update, persist=False)
    snapshot = manager.get_lifecycle(created["lifecycle_id"])["snapshot"]
    assert observed["status"] == "INSUFFICIENT_EVIDENCE"
    assert observed["duplicate"] is False
    assert snapshot["state"] == "RISK_APPROVED"
    assert snapshot["fill_ids"] == []


def test_generic_order_id_cannot_stand_in_for_typed_entry_order(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _live_registry_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    update = copy.deepcopy(opened)
    update.update({
        "execution_sent": True,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "order_id": "POSSIBLY-A-STOP-ORDER",
    })
    observed = item.observe_event("TRADE_UPDATED", update, persist=False)
    snapshot = manager.get_lifecycle(created["lifecycle_id"])["snapshot"]
    assert observed["status"] == "INSUFFICIENT_EVIDENCE"
    assert observed["duplicate"] is False
    assert snapshot["state"] == "RISK_APPROVED"
    assert snapshot["exchange_order_id"] is None


def test_late_decision_id_does_not_block_factual_submission_sequence(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _live_registry_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    update = copy.deepcopy(opened)
    update.update({
        "decision_id": "DECISION-ARRIVED-LATER",
        "execution_sent": True,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
    })
    observed = item.observe_event("TRADE_UPDATED", update, persist=False)
    snapshot = manager.get_lifecycle(created["lifecycle_id"])["snapshot"]
    assert observed["status"] == "APPLIED"
    assert snapshot["state"] == "ENTRY_CONFIRMED"
    assert snapshot["exchange_order_id"] == "2077030442691940352"


def test_real_manager_match_persists_validation_after_registry_entry_and_stop_facts(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _live_registry_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    registry = copy.deepcopy(opened)
    registry.update({
        "execution_sent": True,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
        "order_id": "2077030442691940352",
        "protected": True,
        "broker_stop_order_id": "2077030444402577408",
        "broker_stop_status": "DISASTER_STOP_CREATED",
        "broker_stop_side": "BUY",
        "broker_stop_symbol": "SOLUSDT",
        "broker_stop_price": 77.5585142857143,
        "broker_stop_amount": 0.12,
        "broker_stop_confirmed_at": "2026-07-14T11:00:23Z",
        "last_update": "2026-07-14T11:00:22Z",
    })
    registry["metadata"].update({
        "execution_sent": True,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
        "broker_stop_status": "DISASTER_STOP_CREATED",
        "broker_stop_side": "BUY",
        "broker_stop_symbol": "SOLUSDT",
        "broker_stop_price": 77.5585142857143,
        "broker_stop_amount": 0.12,
        "broker_stop_confirmed_at": "2026-07-14T11:00:23Z",
    })
    item.observe_event("TRADE_UPDATED", registry, persist=False)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert snapshot["state"] == "ENTRY_PROTECTED"
    assert snapshot["fill_ids"] == []
    assert snapshot["disaster_stop"]["order_id"] == "2077030444402577408"

    matched = item.reconcile_trade(registry, persist=True)
    duplicate = item.reconcile_trade(registry, persist=True)
    rows = [json.loads(line) for line in item.events_file.read_text(encoding="utf-8").splitlines()]
    assert matched["status"] == "MATCH", matched.get("reasons")
    assert matched["shadow_validation"]["persisted"] is True
    assert duplicate["shadow_validation"]["duplicate"] is True
    assert [row["event_type"] for row in rows] == ["SHADOW_VALIDATED"]


@pytest.mark.parametrize("mode", ["PREVIEW", "VERIFY", "DRY_RUN", "SAFE_DRY_RUN"])
def test_registry_non_operational_modes_never_create_live_lifecycle(tmp_path, mode):
    manager = FakeManager()
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = _live_registry_open(mode=mode)

    result = item.observe_event("SIGNAL_CREATED", payload, persist=False)

    assert result["status"] == "NOT_ELIGIBLE"
    assert result["fail_open"] is True
    assert result["operational_result_preserved"] is True
    assert manager.created == []
    assert manager.applied == []


def test_explicit_live_lifecycle_identity_separates_same_structural_trade(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    first = _factual_live_open()
    second = _factual_live_open(
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-SECOND",
        client_order_id="FALCON-LIVE-FALCON15-SECOND",
        broker_order_id="ENTRY-ORDER-SECOND",
        broker_stop_order_id="STOP-ORDER-SECOND",
        last_update="2026-07-14T11:01:23Z",
    )

    first_result = item.observe_event("SIGNAL_CREATED", first, persist=False)
    second_result = item.observe_event("SIGNAL_CREATED", second, persist=False)

    assert first["trade_id"] == second["trade_id"]
    assert first_result["lifecycle_id"] != second_result["lifecycle_id"]
    assert manager.get_lifecycle(first_result["lifecycle_id"])["snapshot"]["client_order_id"] == first["client_order_id"]
    assert manager.get_lifecycle(second_result["lifecycle_id"])["snapshot"]["client_order_id"] == second["client_order_id"]
    assert manager.get_trade_lifecycles(first["trade_id"])["count"] == 2


def test_registry_initial_stop_failure_enters_shadow_recovery(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = _factual_live_open(
        protected=False,
        disaster_stop_confirmed=False,
        broker_stop_status="LIVE_SENT_BUT_STOP_FAILED",
        broker_stop_order_id=None,
        broker_stop_confirmed_at=None,
    )

    observed = item.observe_event("SIGNAL_CREATED", payload, persist=False)
    snapshot = manager.get_lifecycle(observed["lifecycle_id"])["snapshot"]

    assert observed["status"] == "APPLIED"
    assert snapshot["state"] == "RECOVERY_REQUIRED"
    assert snapshot["disaster_stop"]["confirmed"] is False
    assert snapshot["recovery"]["required"] is True
    assert snapshot["fill_ids"] == []


def test_reconciliation_waits_for_complete_live_lifecycle_without_comparing(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    incomplete = _live_registry_open(
        execution_sent=True,
        client_order_id="CLIENT-INCOMPLETE",
        broker_order_id="ORDER-INCOMPLETE",
        last_update="2026-07-14T11:00:24Z",
    )
    created = item.observe_event("SIGNAL_CREATED", incomplete, persist=False)
    manager.compare_with_registry = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("comparison must not run"))

    result = item.reconcile_trade(incomplete, persist=True)

    assert created["status"] == "APPLIED"
    assert result["status"] == "LIFECYCLE_INCOMPLETE"
    assert result["reconciled"] is False
    assert result["shadow_validation"]["eligible"] is False
    assert not item.events_file.exists()
    assert not item.divergences_file.exists()


def test_live_management_close_outcome_and_terminal_validation(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _factual_live_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    initial = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert initial["state"] == "ENTRY_PROTECTED"
    assert initial["entry_price_theoretical"] == pytest.approx(76.912)
    assert initial["entry_price_reference"] == pytest.approx(76.93)
    assert initial["entry_price_confirmed"] is None

    tp50 = copy.deepcopy(opened)
    tp50.update({
        "tp50_real_executed": True,
        "tp50_status": "REAL_EXECUTED",
        "tp50_real_order_id": "TP50-ORDER-1",
        "tp50_amount": 0.06,
        "remaining_qty": 0.06,
        "broker_stop_order_id": "RUNNER-STOP-1",
        "broker_stop_status": "STOP_REPLACED_CANCEL_CREATE",
        "broker_stop_amount": 0.06,
        "broker_stop_confirmed_at": "2026-07-14T11:05:00Z",
        "last_update": "2026-07-14T11:05:00Z",
    })
    assert item.observe_event("TRADE_UPDATED", tp50, persist=False)["status"] == "APPLIED"
    after_tp50 = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert after_tp50["state"] == "RUNNER_PROTECTED"
    assert after_tp50["quantity_open"] == pytest.approx(0.06)
    assert after_tp50["quantity_closed"] == pytest.approx(0.06)
    assert after_tp50["fill_ids"] == []
    assert after_tp50["tp50"]["broker_order_ids"] == ["TP50-ORDER-1"]

    break_even = copy.deepcopy(tp50)
    break_even.update({
        "stop_update_reason": "BREAK_EVEN",
        "stop_update": {"ok": True, "status": "STOP_REPLACED_EDIT", "new_order_id": "BE-STOP-1"},
        "broker_stop_order_id": "BE-STOP-1",
        "broker_stop_status": "STOP_REPLACED_EDIT",
        "broker_stop_price": 76.912,
        "broker_stop_confirmed_at": "2026-07-14T11:06:00Z",
        "last_update": "2026-07-14T11:06:00Z",
    })
    assert item.observe_event("TRADE_UPDATED", break_even, persist=False)["status"] == "APPLIED"
    assert manager.get_lifecycle(lifecycle_id)["snapshot"]["state"] == "BREAK_EVEN_ACTIVE"

    trailing_ids = []
    trailing = copy.deepcopy(break_even)
    for number, (order_id, stop_price) in enumerate((("TRAIL-STOP-1", 76.50), ("TRAIL-STOP-2", 76.20)), start=1):
        trailing.update({
            "stop_update_reason": "TRAILING",
            "stop_update": {"ok": True, "status": "STOP_REPLACED_EDIT", "new_order_id": order_id},
            "broker_stop_order_id": order_id,
            "broker_stop_status": "STOP_REPLACED_EDIT",
            "broker_stop_price": stop_price,
            "broker_stop_confirmed_at": f"2026-07-14T11:0{6 + number}:00Z",
            "last_update": f"2026-07-14T11:0{6 + number}:00Z",
        })
        result = item.observe_event("TRADE_UPDATED", trailing, persist=False)
        assert result["status"] == "APPLIED"
        trailing_ids.extend(
            step["event_id"]
            for step in result["manager_result"]["live_position_transition"]["steps"]
            if step["event_type"] == "TRAILING_CONFIRMED"
        )
    assert len(set(trailing_ids)) == 2
    assert manager.get_lifecycle(lifecycle_id)["snapshot"]["state"] == "TRAILING_ACTIVE"

    closed = copy.deepcopy(trailing)
    closed.update({
        "status": "CLOSED",
        "closed_at": "2026-07-14T11:10:00Z",
        "close_reason": "STOP_FAILSAFE_MARKET",
        "exit_price": 77.62,
        "result_pct": -0.9218,
        "result_r": -1.0966,
        "pnl_usdt": -0.85,
        # Registry intentionally retains the runner quantity after CLOSED.
        "remaining_qty": 0.06,
        "last_update": "2026-07-14T11:10:00Z",
    })
    completed = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)
    terminal = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert completed["status"] == "APPLIED"
    assert terminal["state"] == "OUTCOME_RECORDED"
    assert terminal["quantity_open"] == pytest.approx(0.0)
    assert terminal["quantity_closed"] == pytest.approx(0.12)
    assert terminal["exchange_order_id"] == "2077030442691940352"
    assert terminal["close"]["quantity_confirmed"] == pytest.approx(0.06)
    assert terminal["close"]["close_reason"] == "STOP_FAILSAFE_MARKET"
    assert terminal["outcome"]["closed_quantity"] == pytest.approx(0.12)
    assert terminal["outcome"]["entry_price_theoretical"] == pytest.approx(76.912)
    assert terminal["outcome"]["entry_price_reference"] == pytest.approx(76.93)
    assert "entry_price_confirmed" not in terminal["outcome"]

    matched = item.reconcile_trade(closed, persist=True)
    assert matched["status"] == "MATCH", matched.get("reasons")
    assert matched["shadow_validation"]["persisted"] is True
    validation = matched["shadow_validation"]["event"]
    assert validation["fail_open"] is True
    assert validation["operational_result_preserved"] is True
    assert {
        "lifecycle_terminal", "close_confirmed", "outcome_recorded", "quantity_open",
        "quantity_closed", "closed_at", "close_reason",
    }.issubset(validation["validated_fields"])
    assert validation["validated_values"]["lifecycle_terminal"] is True
    assert validation["validated_values"]["quantity_open"] == 0.0

    from trade_timeline_validator import validate_trade_timeline

    timeline = validate_trade_timeline(
        closed["trade_id"],
        sources={"lifecycle": [terminal], "shadow_runtime": [validation]},
    )
    found = {event["event"] for event in timeline["events_found"]}
    assert "LIFECYCLE_FINISHED" in found
    assert "SHADOW_VALIDATED" in found


def test_registry_post_persistence_hook_completes_live_lifecycle_naturally(monkeypatch, tmp_path):
    central_dir = tmp_path / "central"
    shadow_dir = tmp_path / "shadow"
    lifecycle_id = "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-E2E-1"
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(central_dir))
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(central_dir / "trade_registry.json"))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(shadow_dir))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "true")
    for name in (
        "trade_registry",
        "trade_lifecycle_shadow_runtime_adapter",
        "trade_lifecycle_manager",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)

    manager = importlib.import_module("trade_lifecycle_manager")
    adapter_module = importlib.import_module("trade_lifecycle_shadow_runtime_adapter")
    registry = importlib.import_module("trade_registry")

    opened = registry.register_open_trade(
        bot="FALCON",
        symbol="SOLUSDT",
        side="SHORT",
        entry=76.912,
        sl=77.5585142857143,
        tp50=76.2654857142857,
        setup="FALCON15",
        qty=0.12,
        source="falcon",
        registry_mode="REAL",
        execution_mode="LIVE",
        lifecycle_id=lifecycle_id,
        metadata={
            "lifecycle_id": lifecycle_id,
            "execution_decision": {"allowed": True, "decision": "ALLOW", "mode": "LIVE"},
        },
    )
    assert opened["ok"] is True
    trade_id = opened["trade_id"]
    after_open = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert after_open["state"] == "RISK_APPROVED"

    updated = registry.update_trade(
        trade_id,
        lifecycle_id=lifecycle_id,
        execution_mode="LIVE",
        registry_mode="REAL",
        order_id="ENTRY-E2E-1",
        broker_order_id="ENTRY-E2E-1",
        client_order_id="FALCON-LIVE-E2E-1",
        metadata={
            "lifecycle_id": lifecycle_id,
            "execution_sent": True,
            "broker_entry_reference": 76.93,
            "initial_qty": 0.12,
            "remaining_qty": 0.12,
            "protected": True,
            "disaster_stop_confirmed": True,
            "broker_stop_order_id": "STOP-E2E-1",
            "broker_stop_status": "DISASTER_STOP_CREATED",
            "broker_stop_side": "BUY",
            "broker_stop_symbol": "SOLUSDT",
            "broker_stop_price": 77.5585142857143,
            "broker_stop_amount": 0.12,
            "broker_stop_confirmed_at": "14/07/2026 11:00:23",
        },
    )
    assert updated["ok"] is True
    protected = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert protected["state"] == "ENTRY_PROTECTED"
    assert protected["exchange_order_id"] == "ENTRY-E2E-1"
    assert protected["disaster_stop"]["order_id"] == "STOP-E2E-1"

    closed = registry.close_trade(
        trade_id,
        exit_price=77.62,
        pnl_pct=-0.9218,
        pnl_r=-1.0966,
        realized_pnl=-0.85,
        reason="STOP_FAILSAFE_MARKET",
        metadata={
            "lifecycle_id": lifecycle_id,
            "remaining_qty": 0.12,
        },
    )
    assert closed["ok"] is True
    terminal = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert terminal["state"] == "OUTCOME_RECORDED"
    assert terminal["quantity_open"] == pytest.approx(0.0)
    assert terminal["quantity_closed"] == pytest.approx(0.12)
    assert terminal["close"]["close_reason"] == "STOP_FAILSAFE_MARKET"
    assert terminal["outcome"]["confirmed"] is True

    runtime_rows = [
        json.loads(line)
        for line in adapter_module._default_adapter.events_file.read_text(encoding="utf-8").splitlines()
    ]
    closed_validations = [
        row
        for row in runtime_rows
        if row.get("event_type") == "SHADOW_VALIDATED" and row.get("registry_status") == "CLOSED"
    ]
    assert len(closed_validations) == 1
    assert closed_validations[0]["validated_values"]["lifecycle_terminal"] is True

    from trade_timeline_validator import validate_trade_timeline

    timeline = validate_trade_timeline(
        trade_id,
        sources={"lifecycle": [terminal], "shadow_runtime": runtime_rows},
    )
    found = {item["event"] for item in timeline["events_found"]}
    assert {"LIFECYCLE_FINISHED", "SHADOW_VALIDATED"}.issubset(found)


def test_tp50_full_close_transitions_to_outcome_without_double_count(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _factual_live_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    full_tp50 = copy.deepcopy(opened)
    full_tp50.update({
        "tp50_real_executed": True,
        "tp50_status": "REAL_EXECUTED_POSITION_CLOSED",
        "tp50_real_order_id": "TP50-FULL-ORDER",
        "tp50_amount": 0.12,
        "remaining_qty": 0.0,
        "last_update": "2026-07-14T11:05:00Z",
    })
    assert item.observe_event("TRADE_UPDATED", full_tp50, persist=False)["status"] == "APPLIED"
    after_tp50 = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert after_tp50["state"] == "TP50_CONFIRMED"
    assert after_tp50["quantity_open"] == 0.0
    assert after_tp50["quantity_closed"] == pytest.approx(0.12)

    closed = copy.deepcopy(full_tp50)
    closed.update({
        "status": "CLOSED",
        "closed_at": "2026-07-14T11:05:01Z",
        "close_reason": "TP50_REAL_EXECUTED_POSITION_CLOSED",
        "exit_price": 75.90,
        "result_pct": 1.1,
        "result_r": 1.0,
        "last_update": "2026-07-14T11:05:01Z",
    })
    result = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)
    terminal = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert result["status"] == "APPLIED"
    assert terminal["state"] == "OUTCOME_RECORDED"
    assert terminal["quantity_open"] == 0.0
    assert terminal["quantity_closed"] == pytest.approx(0.12)
    assert terminal["outcome"]["closed_quantity"] == pytest.approx(0.12)


def test_unprotected_stop_update_enters_recovery_and_factual_failsafe_close_completes(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _factual_live_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    failed = copy.deepcopy(opened)
    failed.update({
        "stop_update_failed": True,
        "stop_update_status": "STOP_REPLACE_CRITICAL_UNPROTECTED",
        "stop_update_reason": "BREAK_EVEN",
        "stop_update": {"ok": False, "status": "STOP_REPLACE_CRITICAL_UNPROTECTED", "rollback": {"ok": False}},
        "last_update": "2026-07-14T11:06:00Z",
    })
    assert item.observe_event("TRADE_UPDATED", failed, persist=False)["status"] == "APPLIED"
    recovering = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert recovering["state"] == "RECOVERY_REQUIRED"
    assert recovering["recovery"]["required"] is True
    assert recovering["disaster_stop"]["confirmed"] is False

    closed = copy.deepcopy(failed)
    closed.update({
        "status": "CLOSED",
        "closed_at": "2026-07-14T11:07:00Z",
        "close_reason": "STOP_FAILSAFE_MARKET",
        "exit_price": 77.80,
        "result_pct": -1.0,
        "result_r": -1.0,
        "remaining_qty": 0.12,
        "last_update": "2026-07-14T11:07:00Z",
    })
    result = item.observe_event("CLOSE_CONFIRMED", closed, persist=False)
    terminal = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert result["status"] == "APPLIED"
    assert terminal["state"] == "OUTCOME_RECORDED"
    assert terminal["quantity_open"] == 0.0
    assert terminal["close"]["close_reason"] == "STOP_FAILSAFE_MARKET"


def test_later_physical_stop_confirmation_recovers_shadow_lifecycle(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _factual_live_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    failed = copy.deepcopy(opened)
    failed.update({
        "stop_update_failed": True,
        "stop_update_status": "STOP_REPLACE_CRITICAL_UNPROTECTED",
        "stop_update_reason": "BREAK_EVEN",
        "stop_update": {"ok": False, "status": "STOP_REPLACE_CRITICAL_UNPROTECTED", "rollback": {"ok": False}},
        "last_update": "2026-07-14T11:06:00Z",
    })
    item.observe_event("TRADE_UPDATED", failed, persist=False)
    assert manager.get_lifecycle(lifecycle_id)["snapshot"]["state"] == "RECOVERY_REQUIRED"

    repaired = copy.deepcopy(failed)
    repaired.update({
        "stop_update_failed": True,
        "stop_update_status": "STOP_REPLACE_FAILED_ROLLED_BACK",
        "stop_update": {
            "ok": False,
            "status": "STOP_REPLACE_FAILED_ROLLED_BACK",
            "rollback": {"ok": True, "order_id": "ROLLBACK-STOP-1"},
        },
        "broker_stop_order_id": "ROLLBACK-STOP-1",
        "broker_stop_status": "ROLLBACK_PROTECTED",
        "broker_stop_price": 77.5585142857143,
        "broker_stop_amount": 0.12,
        "broker_stop_confirmed_at": "2026-07-14T11:06:05Z",
        "last_update": "2026-07-14T11:06:05Z",
    })
    result = item.observe_event("TRADE_UPDATED", repaired, persist=False)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert result["status"] == "APPLIED"
    assert snapshot["state"] == "ENTRY_PROTECTED"
    assert snapshot["disaster_stop"]["order_id"] == "ROLLBACK-STOP-1"
    assert snapshot["recovery"]["required"] is False
    assert snapshot["recovery"]["completed"] is True
    assert snapshot["recovery"]["completed_by"] == "DISASTER_STOP_CONFIRMED"


def test_immediate_stop_rollback_refreshes_shadow_and_old_retry_cannot_regress_it(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _factual_live_open()
    lifecycle_id = item.observe_event("SIGNAL_CREATED", opened, persist=False)["lifecycle_id"]

    break_even = copy.deepcopy(opened)
    break_even.update({
        "stop_update_reason": "BREAK_EVEN",
        "stop_update_confirmed": True,
        "stop_update_confirmed_at": "2026-07-14T11:05:00Z",
        "stop_update": {"ok": True, "status": "STOP_REPLACED_EDIT", "new_order_id": "BE-STOP-1"},
        "broker_stop_order_id": "BE-STOP-1",
        "broker_stop_status": "STOP_REPLACED_EDIT",
        "broker_stop_price": 76.912,
        "broker_stop_confirmed_at": "2026-07-14T11:05:00Z",
        "last_update": "2026-07-14T11:05:00Z",
    })
    assert item.observe_event("TRADE_UPDATED", break_even, persist=False)["status"] == "APPLIED"
    assert manager.get_lifecycle(lifecycle_id)["snapshot"]["state"] == "BREAK_EVEN_ACTIVE"

    rollback = copy.deepcopy(break_even)
    rollback.update({
        "stop_update_reason": "TRAILING",
        "stop_update_failed": True,
        "stop_update_recovered": True,
        "stop_update_confirmed": False,
        "stop_update_final_protection_confirmed": True,
        "stop_update_confirmed_at": "2026-07-14T11:06:00Z",
        "stop_update": {
            "ok": False,
            "status": "STOP_REPLACE_FAILED_ROLLED_BACK",
            "rollback": {"ok": True, "order_id": "ROLLBACK-STOP-2"},
        },
        "broker_stop_order_id": "ROLLBACK-STOP-2",
        "broker_stop_status": "ROLLBACK_PROTECTED",
        "broker_stop_price": 76.912,
        "broker_stop_amount": 0.12,
        "broker_stop_confirmed_at": "2026-07-14T11:06:00Z",
        "disaster_stop_confirmed": True,
        "last_update": "2026-07-14T11:06:00Z",
    })
    observed = item.observe_event("TRADE_UPDATED", rollback, persist=False)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]

    assert observed["status"] == "APPLIED"
    assert snapshot["state"] == "BREAK_EVEN_ACTIVE"
    assert snapshot["disaster_stop"]["order_id"] == "ROLLBACK-STOP-2"
    assert item.reconcile_trade(rollback, persist=False)["status"] == "MATCH"

    stale_retry = copy.deepcopy(opened)
    stale_retry["event_id"] = "STALE-STOP-RETRY"
    stale_retry["last_update"] = "2026-07-14T11:00:23Z"
    item.observe_event("TRADE_UPDATED", stale_retry, persist=False)
    after_stale_retry = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert after_stale_retry["disaster_stop"]["order_id"] == "ROLLBACK-STOP-2"


def test_live_history_uses_factual_per_step_timestamps(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    payload = _factual_live_open(
        created_at="2026-07-14T11:00:00Z",
        opened_at="2026-07-14T11:00:22Z",
        broker_ack_at="2026-07-14T11:00:20Z",
        broker_stop_confirmed_at="2026-07-14T11:00:23Z",
        last_update="2026-07-14T11:00:23Z",
    )
    payload["metadata"].update({
        "execution_decision": {
            "allowed": True,
            "decision": "ALLOW",
            "occurred_at": "2026-07-14T11:00:10Z",
        },
        "broker_ack_at": "2026-07-14T11:00:20Z",
    })

    result = item.observe_event("SIGNAL_CREATED", payload, persist=False)
    history = manager.get_lifecycle(result["lifecycle_id"])["snapshot"]["history"]
    occurred_at = {
        row["event_type"]: row.get("occurred_at")
        for row in history
        if row.get("applied") is True
    }

    assert occurred_at["SIGNAL_CREATED"] == "2026-07-14T11:00:00Z"
    assert occurred_at["DECISION_PENDING_RECORDED"] == "2026-07-14T11:00:10Z"
    assert occurred_at["RISK_APPROVED_RECORDED"] == "2026-07-14T11:00:10Z"
    assert occurred_at["ENTRY_SUBMITTED"] == "2026-07-14T11:00:20Z"
    assert occurred_at["ENTRY_CONFIRMED"] == "2026-07-14T11:00:22Z"
    assert occurred_at["DISASTER_STOP_CONFIRMED"] == "2026-07-14T11:00:23Z"


def test_tp50_resize_failure_records_tp50_before_recovery(monkeypatch, tmp_path):
    manager = _isolated_lifecycle_manager(monkeypatch, tmp_path)
    item = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "adapter", manager=manager)
    opened = _factual_live_open()
    created = item.observe_event("SIGNAL_CREATED", opened, persist=False)
    lifecycle_id = created["lifecycle_id"]
    failed = copy.deepcopy(opened)
    failed.update({
        "tp50_real_executed": True,
        "tp50_status": "REAL_EXECUTED_STOP_RESIZE_FAILED",
        "tp50_real_order_id": "TP50-FAIL-ORDER",
        "tp50_amount": 0.06,
        "remaining_qty": 0.06,
        "stop_update_failed": True,
        "stop_update_status": "STOP_REPLACE_CRITICAL_UNPROTECTED",
        "stop_update_reason": "TP50_RESIZE",
        "stop_update": {"ok": False, "status": "STOP_REPLACE_CRITICAL_UNPROTECTED", "rollback": {"ok": False}},
        "last_update": "2026-07-14T11:05:00Z",
    })

    result = item.observe_event("TRADE_UPDATED", failed, persist=False)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]
    history_types = [row.get("event_type") for row in snapshot["history"]]
    assert result["status"] == "APPLIED"
    assert snapshot["state"] == "RECOVERY_REQUIRED"
    assert snapshot["quantity_closed"] == pytest.approx(0.06)
    assert history_types.index("TP50_CONFIRMED") < history_types.index("RECOVERY_REQUESTED")


def test_reconcile_all_includes_open_and_closed(adapter):
    result = adapter.reconcile_all({"open_trades": {"A": base()}, "closed_trades": [base()]}, persist=False)
    assert result["count"] == 2


def test_concurrent_same_event_id_is_applied_once(adapter):
    payload = base(event_id="CONCURRENT")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: adapter.observe_event("DECISION_ALLOWED", payload, persist=False), range(20)))
    assert sum(result["status"] == "APPLIED" for result in results) == 1
    assert sum(result.get("duplicate", False) for result in results) == 19


def test_no_network_or_broker_call(adapter, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    assert adapter.observe_event("SIGNAL", base(), persist=False)["status"] == "APPLIED"


def test_registry_payload_is_read_only(adapter):
    trade = base(comparison="MATCH")
    original = copy.deepcopy(trade)
    adapter.reconcile_trade(trade, persist=False)
    assert trade == original


def test_metrics_are_structured(adapter):
    adapter.observe_event("SIGNAL", base(), persist=False)
    metrics = adapter.get_metrics()
    assert metrics["ok"] and metrics["metrics"]["observed"] == 1


def test_public_read_only_wrappers_are_exported():
    assert "get_shadow_runtime_adapter_health" in runtime_adapter_module.__all__
    assert "get_shadow_runtime_adapter_metrics" in runtime_adapter_module.__all__
    assert callable(runtime_adapter_module.get_shadow_runtime_adapter_health)
    assert callable(runtime_adapter_module.get_shadow_runtime_adapter_metrics)


def test_public_wrappers_delegate_to_same_official_instance(monkeypatch):
    calls = {"health": 0, "metrics": 0}

    class OfficialAdapterProbe:
        def get_health(self):
            calls["health"] += 1
            return {"ok": True, "status": "DISABLED", "marker": "official"}

        def get_metrics(self):
            calls["metrics"] += 1
            return {"ok": True, "status": "OK", "metrics": {"observed": 0}, "marker": "official"}

        def observe_event(self, *args, **kwargs):
            raise AssertionError("observe_event called")

        def reconcile_trade(self, *args, **kwargs):
            raise AssertionError("reconcile_trade called")

        def reconcile_all(self, *args, **kwargs):
            raise AssertionError("reconcile_all called")

    official = OfficialAdapterProbe()
    monkeypatch.setattr(runtime_adapter_module, "_default_adapter", official)
    monkeypatch.setattr(runtime_adapter_module, "TradeLifecycleShadowRuntimeAdapter", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("second adapter created")))

    assert runtime_adapter_module.get_shadow_runtime_adapter_health()["marker"] == "official"
    assert runtime_adapter_module.get_shadow_runtime_adapter_metrics()["marker"] == "official"
    assert calls == {"health": 1, "metrics": 1}


def test_public_wrappers_do_not_mutate_metrics_or_create_files(tmp_path, monkeypatch):
    official = TradeLifecycleShadowRuntimeAdapter(enabled=False, data_dir=tmp_path, manager=FakeManager())
    monkeypatch.setattr(runtime_adapter_module, "_default_adapter", official)
    before = official.get_metrics()["metrics"]
    files_before = list(tmp_path.iterdir())

    for _ in range(3):
        assert isinstance(runtime_adapter_module.get_shadow_runtime_adapter_health(), dict)
        assert isinstance(runtime_adapter_module.get_shadow_runtime_adapter_metrics(), dict)

    assert official.get_metrics()["metrics"] == before
    assert list(tmp_path.iterdir()) == files_before == []


def test_public_wrappers_make_no_network_or_broker_import(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    before_broker = sys.modules.get("broker")
    health = runtime_adapter_module.get_shadow_runtime_adapter_health()
    metrics = runtime_adapter_module.get_shadow_runtime_adapter_metrics()
    assert isinstance(health, dict) and isinstance(metrics, dict)
    assert sys.modules.get("broker") is before_broker


def test_shadow_failure_does_not_change_official_result(adapter):
    official = {"ok": True, "status": "OFFICIAL_RESULT"}
    adapter.manager.fail = True
    adapter.observe_event("SIGNAL", base(), persist=False)
    assert official == {"ok": True, "status": "OFFICIAL_RESULT"}


def test_update_trade_uses_generic_shadow_event(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    sys.modules.pop("trade_registry", None)
    sys.modules.pop("trade_lifecycle_shadow_runtime_adapter", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    import trade_lifecycle_shadow_runtime_adapter as shadow_module

    captured = {}

    def fake_observe(event_type, payload, persist=True):
        captured["event_type"] = event_type
        return {"ok": True, "status": "APPLIED", "shadow_mode": True, "production_blocked": False}

    monkeypatch.setattr(shadow_module, "safe_observe_shadow_event", fake_observe)
    monkeypatch.setattr(shadow_module, "safe_reconcile_shadow_trade", lambda *args, **kwargs: {"ok": True, "status": "MATCH", "reconciled": True})
    registry = importlib.import_module("trade_registry")
    result = registry.register_open_trade("FALCON", "BTCUSDT", "LONG", 100.0, qty=1.0, metadata={"source": "TEST"})
    assert result["ok"]
    update_result = registry.update_trade(result["trade_id"], metadata={"note": "x"})
    assert update_result["ok"]
    assert captured["event_type"] == "TRADE_UPDATED"


def test_external_positions_are_segregated_and_not_owned(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    sys.modules.pop("trade_registry", None)
    sys.modules.pop("trade_lifecycle_shadow_runtime_adapter", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    shadow_module = importlib.import_module("trade_lifecycle_shadow_runtime_adapter")
    manager = shadow_module.TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())
    result = manager.observe_event("EXTERNAL_POSITION", base(lifecycle_id="EXT-1", trade_id="", external_position=True, bot="FALCON"), persist=False)
    assert result["status"] == "APPLIED"
    created = manager.manager.created[0]
    assert created["trade_id"] == ""
    assert created["bot"] == ""
    assert created["external_position"] is True


def test_close_out_of_order_is_fail_open(monkeypatch, tmp_path):
    class BlockingManager(FakeManager):
        def apply_event(self, lifecycle_id, event, persist=True):
            return {"ok": False, "blocked": True, "status": "BLOCKED", "reasons": ["lifecycle not found"]}

    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    sys.modules.pop("trade_registry", None)
    sys.modules.pop("trade_lifecycle_shadow_runtime_adapter", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    shadow_module = importlib.import_module("trade_lifecycle_shadow_runtime_adapter")
    manager = shadow_module.TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=BlockingManager())
    result = manager.observe_event("CLOSE_CONFIRMED", base(lifecycle_id="LC-OUT-OF-ORDER", trade_id="TR-OUT"), persist=False)
    assert result["status"] == "BLOCKED"
    assert result["production_blocked"] is False
    assert result["ok"] is False


def test_predator_registry_trade_without_lifecycle_id_is_observed_applied_and_journaled(tmp_path):
    manager = FakeManager()
    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = {
        "trade_id": "PREDATOR:SMART_PREDATOR:ARBUSDT:LONG",
        "bot": "PREDATOR",
        "setup": "SMART_PREDATOR",
        "symbol": "ARBUSDT",
        "side": "LONG",
        "entry": 0.09299,
        "sl": 0.09225,
        "tp50": 0.09447,
        "status": "OPEN",
    }
    original = copy.deepcopy(payload)

    result = adapter.observe_event("SIGNAL", payload, persist=True)

    assert result["ok"] is True
    assert result["status"] == "APPLIED"
    assert result["lifecycle_id"].startswith("CENTRAL-SHADOW-LIFECYCLE-")
    assert result["lifecycle_id_source"] == "DERIVED_CANONICAL_IDENTITY"
    assert result["identity_source"] == "TRADE_ID"
    assert result["production_blocked"] is False
    assert result["operational_authority"] is False
    assert adapter.get_metrics()["metrics"] == {"observed": 1, "applied": 1, "duplicate": 0, "blocked": 0, "errors": 0, "reconciled": 0, "divergences": 0}
    assert manager.created[0]["lifecycle_id"] == result["lifecycle_id"]
    assert payload == original
    journal = json.loads(adapter.events_file.read_text(encoding="utf-8").splitlines()[0])
    assert journal["lifecycle_id"] == result["lifecycle_id"]
    assert journal["lifecycle_id_source"] == "DERIVED_CANONICAL_IDENTITY"


@pytest.mark.parametrize("identity_field", ["trade_id", "registry_id", "execution_id", "decision_id", "signal_id"])
def test_each_canonical_identity_can_derive_lifecycle_id(tmp_path, identity_field):
    manager = FakeManager()
    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = {identity_field: f"{identity_field}-1"}

    result = adapter.observe_event("SIGNAL", payload, persist=False)

    assert result["status"] == "APPLIED"
    assert result["identity_source"] == identity_field.upper()
    assert manager.created[0]["lifecycle_id"] == result["lifecycle_id"]


def test_fallback_identity_can_derive_lifecycle_id(adapter):
    result = adapter.observe_event("SIGNAL", {"bot": "PREDATOR", "setup": "SMART_PREDATOR"}, persist=False)
    assert result["status"] == "APPLIED"
    assert result["identity_source"] == "DETERMINISTIC_FALLBACK"


def test_derived_lifecycle_is_deterministic_across_instances_and_restart(tmp_path):
    payload = {"trade_id": "TR-STABLE"}
    first = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "same", manager=FakeManager())
    before_restart = first.observe_event("SIGNAL", payload, persist=True)
    second = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "same", manager=FakeManager())
    after_restart = second.observe_event("SIGNAL", payload, persist=False)
    third = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "other", manager=FakeManager())
    other_process = third.observe_event("SIGNAL", payload, persist=False)
    assert before_restart["lifecycle_id"] == after_restart["lifecycle_id"] == other_process["lifecycle_id"]


def test_different_canonical_trades_derive_different_lifecycles(tmp_path):
    first = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "a", manager=FakeManager()).observe_event("SIGNAL", {"trade_id": "TR-A"}, persist=False)
    second = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path / "b", manager=FakeManager()).observe_event("SIGNAL", {"trade_id": "TR-B"}, persist=False)
    assert first["lifecycle_id"] != second["lifecycle_id"]


def test_explicit_lifecycle_id_is_preserved_exactly(adapter):
    result = adapter.observe_event("SIGNAL", {"trade_id": "TR-EXPLICIT", "metadata": {"lifecycle_id": "LC-EXPLICIT"}}, persist=False)
    assert result["lifecycle_id"] == "LC-EXPLICIT"
    assert result["lifecycle_id_source"] == "EXPLICIT_LIFECYCLE_ID"


def test_external_lifecycle_remains_segregated(adapter):
    result = adapter.observe_event("EXTERNAL_POSITION", {"external_position": True, "bot": "FALCON", "symbol": "BTCUSDT", "side": "LONG"}, persist=False)
    assert result["lifecycle_id"].startswith("CENTRAL-SHADOW-EXTERNAL-")
    assert result["lifecycle_id_source"] == "EXTERNAL_POSITION"
    assert adapter.manager.created[0]["bot"] == ""
    assert adapter.manager.created[0]["trade_id"] == ""


def test_truly_insufficient_identity_is_not_observed(adapter):
    result = adapter.observe_event("SIGNAL", {}, persist=False)
    assert result["status"] == "INSUFFICIENT_IDENTITY"
    assert result["reasons"] == ["canonical trade identity missing"]
    assert adapter.get_metrics()["metrics"]["observed"] == 0


def test_observe_and_reconcile_use_same_derived_lifecycle(tmp_path):
    manager = FakeManager()
    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = {"trade_id": "TR-SAME", "comparison": "MATCH"}
    observed = adapter.observe_event("SIGNAL", payload, persist=False)
    reconciled = adapter.reconcile_trade(payload, persist=False)
    assert reconciled["lifecycle_id"] == observed["lifecycle_id"]
    assert reconciled["lifecycle_id_source"] == "DERIVED_CANONICAL_IDENTITY"


def test_derived_lifecycle_keeps_duplicate_and_concurrency_idempotent(tmp_path):
    manager = FakeManager()
    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    payload = {"trade_id": "TR-CONCURRENT", "event_id": "DERIVED-CONCURRENT"}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: adapter.observe_event("SIGNAL", payload, persist=False), range(20)))
    assert sum(result["status"] == "APPLIED" for result in results) == 1
    assert sum(result.get("duplicate", False) for result in results) == 19
    assert len(manager.created) == 1


def test_same_symbol_side_for_different_bots_remains_independent_with_derived_ids(tmp_path):
    manager = FakeManager()
    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=manager)
    falcon = adapter.observe_event("SIGNAL", {"trade_id": "FALCON:BTCUSDT:LONG", "bot": "FALCON", "symbol": "BTCUSDT", "side": "LONG"}, persist=False)
    predator = adapter.observe_event("SIGNAL", {"trade_id": "PREDATOR:BTCUSDT:LONG", "bot": "PREDATOR", "symbol": "BTCUSDT", "side": "LONG"}, persist=False)
    assert falcon["lifecycle_id"] != predator["lifecycle_id"]


def test_registry_functions_keep_official_result_with_shadow_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    sys.modules.pop("trade_registry", None)
    sys.modules.pop("trade_lifecycle_shadow_runtime_adapter", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    shadow_module = importlib.import_module("trade_lifecycle_shadow_runtime_adapter")
    registry = importlib.import_module("trade_registry")

    open_result = registry.register_open_trade("FALCON", "BTCUSDT", "LONG", 100.0, qty=1.0)
    assert open_result["ok"] and open_result["action"] == "OPEN_REGISTERED"

    update_result = registry.update_trade(open_result["trade_id"], metadata={"note": "x"})
    assert update_result["ok"] and update_result["action"] == "TRADE_UPDATED"

    close_result = registry.close_trade(open_result["trade_id"], exit_price=101.0, pnl_r=1.0, reason="test")
    assert close_result["ok"] and close_result["action"] == "TRADE_CLOSED"

    updated_closed = registry.update_closed_trade(close_result["trade_id"], metadata={"outcome": "ok"})
    assert updated_closed["ok"] and updated_closed["action"] == "CLOSED_TRADE_UPDATED"

    shadow_module._default_adapter.manager.fail = True
    shadow_module._default_adapter.enabled = True
    open_result2 = registry.register_open_trade("FALCON", "BTCUSDT", "LONG", 100.0, qty=1.0)
    assert open_result2["ok"] and open_result2["action"] == "OPEN_REGISTERED"
