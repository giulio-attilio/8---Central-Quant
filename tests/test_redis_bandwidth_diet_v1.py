from __future__ import annotations

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
        self.keys_calls = 0

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

    def keys(self, *args, **kwargs):
        self.keys_calls += 1
        raise AssertionError("KEYS must never be used")


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.setenv("REDIS_BANDWIDTH_INSTRUMENTATION_ENABLED", "true")
    monkeypatch.setenv("REDIS_BANDWIDTH_DIET_ENABLED", "true")
    bandwidth.reset_redis_bandwidth_state(confirm=True)
    yield
    bandwidth.reset_redis_bandwidth_state(confirm=True)


def test_01_set_size_is_measured_without_raw_payload():
    client = FakeRedis()
    secret = "private-order-body-123"
    bandwidth.redis_set(client, "falcon:events", secret, caller="bots.falcon")
    report = bandwidth.redis_bandwidth_report()
    assert report["top_operations_by_bytes"][0]["op"] == "SET"
    assert report["top_operations_by_bytes"][0]["total_bytes"] == len(secret)
    assert secret not in json.dumps(report)


def test_02_get_size_is_measured_without_raw_payload():
    payload = "ç" * 20
    client = FakeRedis({"smartpredator:execution_firewall_events": payload})
    assert bandwidth.redis_get(client, "smartpredator:execution_firewall_events", caller="bots.predator") == payload
    report = bandwidth.redis_bandwidth_report()
    get_row = next(item for item in report["top_operations_by_bytes"] if item["op"] == "GET")
    assert get_row["total_bytes"] == len(payload.encode("utf-8"))
    assert payload not in json.dumps(report)


def test_03_sensitive_payload_never_appears_in_report_or_text():
    client = FakeRedis()
    sensitive = "API_SECRET=should-never-be-reported"
    bandwidth.redis_set(client, "falcon:events", sensitive, caller="bots.falcon")
    rendered = json.dumps(bandwidth.redis_bandwidth_report()) + bandwidth.build_redis_bandwidth_text()
    assert sensitive not in rendered


def test_04_key_sanitization_preserves_category_and_masks_ids():
    key = "cobra:telegram:1234567890:550e8400-e29b-41d4-a716-446655440000"
    sanitized = bandwidth.sanitize_redis_key(key)
    assert sanitized == "cobra:telegram:<id>:<id>"
    assert bandwidth.sanitize_redis_key("https://user:password@redis.invalid/key") == "<redacted-key>"


def test_05_top_keys_are_sorted_by_estimated_bytes():
    client = FakeRedis({"falcon:funnel": "x" * 10, "turtle_pro:events": "x" * 100})
    bandwidth.redis_get(client, "falcon:funnel", caller="falcon", no_cache=True)
    bandwidth.redis_get(client, "turtle_pro:events", caller="turtle", no_cache=True)
    rows = bandwidth.redis_bandwidth_report()["top_keys_by_bytes"]
    assert [item["key"] for item in rows[:2]] == ["turtle_pro:events", "falcon:funnel"]


def test_06_top_operations_are_sorted_by_bytes():
    client = FakeRedis({"falcon:funnel": "x" * 200})
    bandwidth.redis_get(client, "falcon:funnel", caller="falcon", no_cache=True)
    bandwidth.redis_set(client, "cobra:state", "small", caller="cobra", skip_unchanged=False)
    rows = bandwidth.redis_bandwidth_report()["top_operations_by_bytes"]
    assert rows[0]["op"] == "GET"


def test_07_top_callers_are_sorted_by_bytes():
    client = FakeRedis({"falcon:funnel": "x" * 20, "turtle_pro:events": "x" * 150})
    bandwidth.redis_get(client, "falcon:funnel", caller="bots.falcon", no_cache=True)
    bandwidth.redis_get(client, "turtle_pro:events", caller="bots.turtle", no_cache=True)
    rows = bandwidth.redis_bandwidth_report()["top_callers_by_bytes"]
    assert rows[0]["caller"] == "bots.turtle"


def test_08_instrumentation_failure_is_fail_open(monkeypatch):
    client = FakeRedis({"falcon:funnel": "ok"})

    def fail(*args, **kwargs):
        raise RuntimeError("metric failed")

    monkeypatch.setattr(bandwidth, "_record_operation", fail)
    assert bandwidth.redis_get(client, "falcon:funnel", caller="falcon", no_cache=True) == "ok"
    assert client.get_calls == ["falcon:funnel"]


def test_09_disabled_instrumentation_preserves_uncached_unskipped_contract(monkeypatch):
    monkeypatch.setenv("REDIS_BANDWIDTH_INSTRUMENTATION_ENABLED", "false")
    monkeypatch.setenv("REDIS_BANDWIDTH_DIET_ENABLED", "false")
    client = FakeRedis({"falcon:funnel": "same"})
    bandwidth.redis_get(client, "falcon:funnel", caller="falcon")
    bandwidth.redis_get(client, "falcon:funnel", caller="falcon")
    bandwidth.redis_set(client, "falcon:funnel", "same", caller="falcon")
    bandwidth.redis_set(client, "falcon:funnel", "same", caller="falcon")
    assert len(client.get_calls) == 2
    assert len(client.set_calls) == 2
    assert bandwidth.redis_bandwidth_report()["total_ops_observed"] == 0


def test_10_short_cache_reduces_repeated_get():
    client = FakeRedis({"report:events": "payload"})
    first = bandwidth.redis_get(client, "report:events", caller="report", cache_ttl_seconds=10)
    second = bandwidth.redis_get(client, "report:events", caller="report", cache_ttl_seconds=10)
    assert first == second == "payload"
    assert client.get_calls == ["report:events"]
    assert bandwidth.redis_bandwidth_report()["cache_hits"] == 1


def test_11_no_cache_forces_fresh_read_for_critical_decision():
    client = FakeRedis({"falcon:positions": "v1"})
    bandwidth.redis_get(client, "falcon:positions", caller="risk", cache_ttl_seconds=30, no_cache=True)
    client.values["falcon:positions"] = "v2"
    result = bandwidth.redis_get(client, "falcon:positions", caller="risk", cache_ttl_seconds=30, no_cache=True)
    assert result == "v2"
    assert len(client.get_calls) == 2


def test_12_skip_set_unchanged_avoids_rewrite_without_comparison_get():
    client = FakeRedis()
    bandwidth.redis_set(client, "falcon:positions", "{}", caller="falcon")
    bandwidth.redis_set(client, "falcon:positions", "{}", caller="falcon")
    report = bandwidth.redis_bandwidth_report()
    assert client.set_calls == [("falcon:positions", "{}")]
    assert client.get_calls == []
    assert report["sets_skipped"] == 1
    assert report["bytes_avoided_estimated"] == 2


def test_13_ttl_is_applied_only_to_known_temporary_daily_flag():
    client = FakeRedis()
    key = "falcon:daily_summary_sent:2026-07-15"
    bandwidth.redis_set(client, key, "true", caller="falcon")
    assert client.expire_calls == [(key, bandwidth.DEFAULT_DAILY_FLAG_TTL_SECONDS)]


def test_14_permanent_key_never_receives_automatic_ttl():
    client = FakeRedis()
    bandwidth.redis_set(client, "falcon:positions", "{}", caller="falcon")
    bandwidth.redis_set(client, "trade_registry:source_of_truth", "{}", caller="registry")
    assert client.expire_calls == []
    assert bandwidth.classify_redis_key("falcon:positions")["classification"] == "PERMANENT"


def test_15_old_daily_flag_is_reported_and_gets_ttl_on_safe_write():
    client = FakeRedis({"falcon:daily_summary_sent:2020-01-01": "true"})
    key = "falcon:daily_summary_sent:2020-01-01"
    bandwidth.redis_get(client, key, caller="falcon", no_cache=True)
    bandwidth.redis_set(client, key, "true", caller="falcon")
    report = bandwidth.redis_bandwidth_report()
    assert key in report["old_daily_flags"]
    assert client.set_calls == []
    assert client.expire_calls == [(key, bandwidth.DEFAULT_DAILY_FLAG_TTL_SECONDS)]


def test_16_reconciliation_tombstones_are_not_expired_or_deleted():
    client = FakeRedis()
    key = "falcon:central_only_reconcile:tombstones:v1"
    bandwidth.redis_set(client, key, "{}", caller="falcon")
    assert bandwidth.classify_redis_key(key)["classification"] == "PERMANENT"
    assert client.expire_calls == []
    assert not hasattr(client, "delete_calls")


def test_17_text_report_is_serializable_small_and_payload_free():
    client = FakeRedis({"smartpredator:funnel_stats": "x" * 64})
    bandwidth.redis_get(client, "smartpredator:funnel_stats", caller="bots.predator", no_cache=True)
    report = bandwidth.redis_bandwidth_report()
    text = bandwidth.build_redis_bandwidth_text()
    json.dumps(report)
    assert text.startswith("REDIS BANDWIDTH DIET V1")
    assert len(text.encode("utf-8")) < 64 * 1024
    assert "x" * 64 not in text


def test_18_diagnostic_report_uses_no_redis_keys_scan_or_get():
    client = FakeRedis({"falcon:funnel": "payload"})
    bandwidth.redis_get(client, "falcon:funnel", caller="falcon", no_cache=True)
    before = list(client.get_calls)
    bandwidth.redis_bandwidth_report()
    bandwidth.build_redis_bandwidth_text()
    assert client.get_calls == before
    assert client.keys_calls == 0


def test_19_existing_bots_route_remains_present():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert '@app.route("/bots")' in source
    assert "def bots():" in source


def test_20_falcon_redis_wrappers_remain_available_and_instrumented():
    source = (ROOT / "bots" / "falcon.py").read_text(encoding="utf-8")
    assert "def redis_get_json(key, default):" in source
    assert "def redis_set_json(key, value):" in source
    assert "bandwidth_redis_get(redis, key, caller=__name__)" in source


def test_21_predator_audit_storage_remains_available_and_instrumented():
    source = (ROOT / "bots" / "predator.py").read_text(encoding="utf-8")
    assert "PREDATOR_EXECUTION_FIREWALL_LOG_KEY" in source
    assert "def carregar_predator_execution_firewall_events" in source
    assert "bandwidth_redis_set(redis, key" in source


def test_22_trade_registry_source_is_not_imported_or_modified_by_helper():
    source = (ROOT / "redis_bandwidth.py").read_text(encoding="utf-8").lower()
    assert "import trade_registry" not in source
    assert "from trade_registry" not in source
    assert "client.delete" not in source


def test_23_helper_has_no_broker_exchange_or_order_authority():
    source = (ROOT / "redis_bandwidth.py").read_text(encoding="utf-8").lower()
    forbidden = ("import broker", "import exchange_manager", "create_order", "cancel_order", "close_position")
    assert all(token not in source for token in forbidden)


def test_24_all_seven_existing_redis_clients_use_central_helper():
    bot_names = ("cobra", "donkey", "falcon", "meme", "predator", "trendpro", "turtle")
    for bot_name in bot_names:
        source = (ROOT / "bots" / f"{bot_name}.py").read_text(encoding="utf-8")
        assert "from redis_bandwidth import" in source
        assert "redis.get(" not in source
        assert "redis.set(" not in source


def test_25_endpoint_routes_are_read_only_and_use_in_memory_report():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert '@app.route("/redis/bandwidth", methods=["GET"])' in source
    assert '@app.route("/redis/bandwidth/text", methods=["GET"])' in source
    assert "return redis_bandwidth_report(limit=20)" in source
    assert "return build_redis_bandwidth_text(limit=20)" in source


def test_26_temporary_unknown_and_permanent_classification_is_conservative():
    assert bandwidth.classify_redis_key("donkey:thread_heartbeat")["classification"] == "TEMPORARY"
    assert bandwidth.classify_redis_key("custom:unreviewed")["classification"] == "UNKNOWN"
    assert bandwidth.ttl_seconds_for_key("custom:unreviewed") is None
    assert bandwidth.classify_redis_key("trade:lifecycle:v1")["classification"] == "PERMANENT"
