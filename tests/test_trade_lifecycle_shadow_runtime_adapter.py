from __future__ import annotations

import copy
import importlib
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

import trade_lifecycle_shadow_runtime_adapter as runtime_adapter_module
from trade_lifecycle_shadow_runtime_adapter import TradeLifecycleShadowRuntimeAdapter


class FakeManager:
    def __init__(self):
        self.created = []
        self.applied = []
        self.fail = False

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
        return {"status": trade.get("comparison", "MATCH"), "differences": trade.get("differences", [])}

    def trade_lifecycle_health(self):
        return {"ok": True, "shadow_mode": True}


@pytest.fixture()
def adapter(tmp_path):
    return TradeLifecycleShadowRuntimeAdapter(enabled=True, data_dir=tmp_path, manager=FakeManager())


def base(**updates):
    item = {"lifecycle_id": "LC-1", "trade_id": "TR-1", "signal_id": "SIG-1", "bot": "FALCON", "setup": "ORB", "symbol": "BTCUSDT", "side": "LONG", "mode": "LIVE", "quantity_planned": 1.0, "timestamp": "2026-07-12T00:00:00Z"}
    item.update(updates)
    return item


def test_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", raising=False)
    item = TradeLifecycleShadowRuntimeAdapter(data_dir=tmp_path, manager=FakeManager())
    assert item.observe_event("SIGNAL", base())["status"] == "DISABLED"


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

    assert result["status"] == "BLOCKED"
    assert result["manager_result"]["current_state"] == "SIGNAL_DETECTED"
    assert result["manager_result"]["paper_position_transition"]["reason"] == "MODE_IS_NOT_PAPER"


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


def test_reconciliation_divergence_is_deduplicated(adapter):
    difference = {"field": "status", "shadow_value": "OPEN", "registry_value": "CLOSED", "severity": "CRITICAL"}
    trade = base(comparison="DIVERGENCE", differences=[difference])
    adapter.reconcile_trade(trade, persist=False)
    adapter.reconcile_trade(trade, persist=False)
    assert adapter.get_metrics()["metrics"]["divergences"] == 1


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
