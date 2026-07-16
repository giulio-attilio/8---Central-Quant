from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import redis_bandwidth as bandwidth


ROOT = Path(__file__).resolve().parents[1]


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.get_calls = []
        self.set_calls = []
        self.expire_calls = []

    def get(self, key):
        self.get_calls.append(key)
        return self.values.get(key)

    def set(self, key, value):
        self.set_calls.append((key, value))
        self.values[key] = value
        return True

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))
        return True


@pytest.fixture(autouse=True)
def reset_bandwidth(monkeypatch):
    monkeypatch.setenv("REDIS_BANDWIDTH_INSTRUMENTATION_ENABLED", "true")
    monkeypatch.setenv("REDIS_BANDWIDTH_DIET_ENABLED", "true")
    monkeypatch.delenv("FALCON_MODE", raising=False)
    monkeypatch.delenv("PREDATOR_MODE", raising=False)
    monkeypatch.setenv("EXECUTION_MODE", "PAPER")
    bandwidth.reset_redis_bandwidth_state(confirm=True)
    yield
    bandwidth.reset_redis_bandwidth_state(confirm=True)


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert matches, name
    return matches[0]


def test_01_falcon_events_hot_key_is_cached_for_sixty_seconds():
    client = FakeRedis({"falcon:events": "large-event-history"})
    for _ in range(3):
        assert bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon") == "large-event-history"
    assert client.get_calls == ["falcon:events"]
    assert bandwidth.safe_cache_seconds_for_key("falcon:events") == 60.0


def test_02_no_cache_remains_available_for_critical_paths():
    client = FakeRedis({"falcon:events": "v1"})
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon", no_cache=True)
    client.values["falcon:events"] = "v2"
    result = bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon", no_cache=True)
    assert result == "v2"
    assert len(client.get_calls) == 2


def test_03_paper_positions_use_short_cache(monkeypatch):
    monkeypatch.setenv("PREDATOR_MODE", "PAPER")
    client = FakeRedis({"smartpredator:positions": "paper-positions"})
    bandwidth.redis_get(client, "smartpredator:positions", caller="central_bots.predator")
    bandwidth.redis_get(client, "smartpredator:positions", caller="central_bots.predator")
    assert client.get_calls == ["smartpredator:positions"]
    assert bandwidth.safe_cache_seconds_for_key("smartpredator:positions", execution_mode="PAPER") == 15.0


def test_04_live_positions_are_always_fresh(monkeypatch):
    monkeypatch.setenv("FALCON_MODE", "LIVE")
    client = FakeRedis({"falcon:positions": "v1"})
    bandwidth.redis_get(client, "falcon:positions", caller="central_bots.falcon")
    client.values["falcon:positions"] = "v2"
    result = bandwidth.redis_get(client, "falcon:positions", caller="central_bots.falcon")
    assert result == "v2"
    assert len(client.get_calls) == 2
    assert bandwidth.redis_key_requires_fresh_read("falcon:positions", execution_mode="LIVE")


def test_05_write_refreshes_safe_cache_with_new_value(monkeypatch):
    monkeypatch.setenv("PREDATOR_MODE", "PAPER")
    client = FakeRedis({"smartpredator:positions": "old"})
    assert bandwidth.redis_get(client, "smartpredator:positions", caller="central_bots.predator") == "old"
    bandwidth.redis_set(client, "smartpredator:positions", "new", caller="central_bots.predator")
    assert bandwidth.redis_get(client, "smartpredator:positions", caller="central_bots.predator") == "new"
    assert client.get_calls == ["smartpredator:positions"]
    assert client.set_calls == [("smartpredator:positions", "new")]


def test_06_turtle_events_trades_and_signals_are_consolidated():
    keys = ("turtle_pro:events", "turtle_pro:trades", "turtle_pro:signals")
    client = FakeRedis({key: key + "-payload" for key in keys})
    for key in keys:
        bandwidth.redis_get(client, key, caller="central_bots.turtle")
        bandwidth.redis_get(client, key, caller="central_bots.turtle")
    assert client.get_calls == list(keys)


def test_07_falcon_history_cache_remains_active_even_when_positions_are_live(monkeypatch):
    monkeypatch.setenv("FALCON_MODE", "LIVE")
    client = FakeRedis({"falcon:events": "events"})
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon")
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon")
    assert client.get_calls == ["falcon:events"]


def test_08_avoided_bytes_are_split_between_cache_and_set_skip():
    client = FakeRedis({"falcon:events": "0123456789"})
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon")
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon")
    bandwidth.redis_set(client, "cobra:state", "x", caller="central_bots.cobra")
    bandwidth.redis_set(client, "cobra:state", "x", caller="central_bots.cobra")
    report = bandwidth.redis_bandwidth_report()
    assert report["bytes_avoided_by_cache"] == 10
    assert report["bytes_avoided_by_set_skipped"] == 1
    assert report["bytes_avoided_estimated"] == 11
    assert report["estimated_savings_after_v2_pct"] > 0


def test_09_report_exposes_largest_average_key_and_v2_hot_status():
    client = FakeRedis({"falcon:events": "x" * 100, "donkey:trades": "y" * 10})
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon", no_cache=True)
    bandwidth.redis_get(client, "donkey:trades", caller="central_bots.donkey", no_cache=True)
    report = bandwidth.redis_bandwidth_report()
    assert report["largest_key_by_avg_bytes_per_call"]["key"] == "falcon:events"
    status = {item["key"]: item for item in report["top_hot_keys_status"]}
    assert status["falcon:events"]["optimized_v2"] is True
    assert status["smartpredator:positions"]["live_positions_no_cache"] is True


def test_10_text_report_is_serializable_and_contains_no_raw_payload():
    secret_payload = "order-secret-payload-never-report"
    client = FakeRedis({"falcon:events": secret_payload})
    bandwidth.redis_get(client, "falcon:events", caller="central_bots.falcon", no_cache=True)
    report = bandwidth.redis_bandwidth_report()
    text = bandwidth.build_redis_bandwidth_text()
    json.dumps(report)
    assert text.startswith("REDIS BANDWIDTH DIET V2")
    assert "Bytes avoided by cache:" in text
    assert "V2 hot key status:" in text
    assert secret_payload not in text
    assert secret_payload not in json.dumps(report)


def test_11_bots_route_uses_light_health_not_full_bot_health():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    node = _function_node(source, "bots")
    calls = {child.func.id for child in ast.walk(node) if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)}
    assert "light_bot_health" in calls
    assert "bot_health" not in calls


def test_12_light_health_has_no_heavy_redis_or_audit_loader():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    node = _function_node(source, "light_bot_health")
    body = ast.get_source_segment(source, node) or ""
    forbidden = (
        "get_positions",
        "carregar_posicoes",
        "get_events",
        "get_trades",
        "get_signals",
        "predator_pnl_paper_audit",
        "predator_paper_lifecycle_audit",
        "trade_registry",
    )
    assert all(name not in body for name in forbidden)
    assert '"heavy_history_loaded": False' in body


def test_13_watchdog_uses_light_health_path():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    node = _function_node(source, "central_watchdog_status")
    calls = {child.func.id for child in ast.walk(node) if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)}
    assert "light_bot_health" in calls
    assert "bot_health" not in calls


def test_14_v1_skip_set_and_daily_ttl_are_preserved():
    client = FakeRedis()
    key = "falcon:daily_summary_sent:2026-07-15"
    bandwidth.redis_set(client, key, "true", caller="central_bots.falcon")
    bandwidth.redis_set(client, key, "true", caller="central_bots.falcon")
    assert client.set_calls == [(key, "true")]
    assert len(client.expire_calls) == 2
    assert bandwidth.redis_bandwidth_report()["sets_skipped"] == 1


def test_15_v2_has_no_order_broker_or_execution_authority():
    source = (ROOT / "redis_bandwidth.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "import broker",
        "import exchange_manager",
        "create_order",
        "cancel_order",
        "close_position",
        "execution_engine",
        "execution_orchestrator",
    )
    assert all(name not in source for name in forbidden)


def test_16_engine_and_orchestrator_are_not_referenced_by_v2_changes():
    helper = (ROOT / "redis_bandwidth.py").read_text(encoding="utf-8")
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    light = ast.get_source_segment(main_source, _function_node(main_source, "light_bot_health")) or ""
    assert "execution_engine" not in helper
    assert "execution_orchestrator" not in helper
    assert "execution_engine" not in light
    assert "execution_orchestrator" not in light
