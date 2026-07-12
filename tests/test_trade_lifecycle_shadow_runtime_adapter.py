from __future__ import annotations

import copy
import importlib
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
    assert result["status"] == "INSUFFICIENT_IDENTITY"
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
