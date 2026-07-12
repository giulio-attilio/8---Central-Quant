import ast
import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import trade_lifecycle_shadow_observability as module
from trade_lifecycle_shadow_observability import TradeLifecycleShadowObservability


def provider_ok():
    return {"ok": True, "status": "ENABLED", "shadow_mode": True}


@pytest.fixture
def obs(tmp_path):
    return TradeLifecycleShadowObservability(
        enabled=True,
        data_dir=tmp_path,
        adapter_health_provider=provider_ok,
        adapter_metrics_provider=lambda: {"ok": True, "metrics": {}},
        lifecycle_health_provider=provider_ok,
        cursor_secret=b"test-secret",
    )


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def append_jsonl(path, rows, incomplete=None):
    with path.open("wb") as handle:
        for row in rows:
            if isinstance(row, bytes):
                handle.write(row + b"\n")
            else:
                handle.write(json.dumps(row).encode("utf-8") + b"\n")
        if incomplete is not None:
            handle.write(incomplete)


def event(index, **overrides):
    snapshot = {
        "trade_id": f"TR-{index}", "bot": "FALCON", "setup": "ORB",
        "symbol": "BTCUSDT", "side": "LONG", "external_position": {},
    }
    item = {
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "event_id": f"EV-{index}", "event_type": "ENTRY_CONFIRMED",
        "lifecycle_id": f"LC-{index}", "identity": {"source": "TRADE_ID"},
        "status": "APPLIED", "manager_result": {"status": "APPLIED", "snapshot": snapshot},
    }
    item.update(overrides)
    return item


def divergence(index=1, **overrides):
    item = {
        "timestamp": datetime(2026, 1, index, tzinfo=timezone.utc).isoformat(),
        "key": f"KEY-{index}", "lifecycle_id": "LC-1", "trade_id": "TR-1",
        "field": "state", "shadow_value": "OPEN", "registry_value": "CLOSED",
        "severity": "CRITICAL", "reason": "different",
    }
    item.update(overrides)
    return item


def test_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(module.ENV_ENABLED, raising=False)
    instance = TradeLifecycleShadowObservability(data_dir=tmp_path)
    assert instance.get_health()["status"] == "DISABLED"
    assert instance.list_events()["items"] == []


def test_health_authorities_and_schema(obs):
    health = obs.get_health()
    assert health["schema_version"] == "1.0"
    for key in ("operational_authority", "broker_access", "registry_write_access", "lifecycle_write_access", "execution_control", "automatic_repair"):
        assert health[key] is False


def test_missing_and_empty_files(obs):
    assert obs.list_events()["items"] == []
    obs.events_file.touch()
    assert obs.list_events()["items"] == []
    assert obs.events_file.stat().st_size == 0


def test_valid_state_metrics(obs):
    write_json(obs.state_file, {"version": "1", "updated_at": datetime.now(timezone.utc).isoformat(), "metrics": {"observed": 7, "applied": 5, "reconciled": 2}})
    result = obs.get_metrics()
    assert result["events"]["observed"] == 7
    assert result["events"]["applied"] == 5
    assert result["reconciliation"]["attempted"] == 2
    assert result["provenance"]["declared_counters"]["source"] == "adapter_state"


def test_invalid_and_stale_state_degrade(obs):
    obs.state_file.write_text("{broken", encoding="utf-8")
    assert obs.get_health()["status"] == "DEGRADED"
    write_json(obs.state_file, {"updated_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "metrics": {}})
    instance = TradeLifecycleShadowObservability(enabled=True, data_dir=obs.data_dir, adapter_health_provider=provider_ok, lifecycle_health_provider=provider_ok, stale_state_seconds=1)
    assert instance.get_health()["status"] == "DEGRADED"


def test_invalid_json_incomplete_and_oversized_are_isolated(obs):
    oversized = b'{"value":"' + (b"x" * (module.MAX_LINE_BYTES + 1)) + b'"}'
    append_jsonl(obs.events_file, [event(1), b"{broken", oversized], incomplete=b'{"event_id":"partial"')
    result = obs.list_events()
    assert len(result["items"]) == 1
    assert result["status"] == "PARTIAL"
    assert result["persistence"]["invalid"] == 1
    assert result["persistence"]["truncated"] == 1
    assert result["persistence"]["incomplete"] == 1


def test_limits_default_maximum_and_rejection(obs):
    append_jsonl(obs.events_file, [event(i) for i in range(210)])
    assert obs.list_events()["page"]["limit"] == 50
    assert obs.list_events(limit=200)["page"]["returned"] == 200
    assert obs.list_events(limit=201)["status"] == "INVALID_LIMIT"


def test_newest_first_and_pagination_without_duplicates(obs):
    rows = [event(i, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()) for i in range(8)]
    append_jsonl(obs.events_file, rows)
    first = obs.list_events(limit=3)
    second = obs.list_events(limit=3, cursor=first["page"]["next_cursor"])
    first_ids = [item["event_id"] for item in first["items"]]
    second_ids = [item["event_id"] for item in second["items"]]
    assert first_ids == ["EV-7", "EV-6", "EV-5"]
    assert not set(first_ids) & set(second_ids)


def test_cursor_tamper_filter_change_and_truncation(obs):
    append_jsonl(obs.events_file, [event(i) for i in range(5)])
    first = obs.list_events(limit=2)
    cursor = first["page"]["next_cursor"]
    assert obs.list_events(limit=2, cursor=cursor[:-1] + ("A" if cursor[-1] != "A" else "B"))["status"] == "INVALID_CURSOR"
    assert obs.list_events({"status": "APPLIED"}, limit=2, cursor=cursor)["status"] == "INVALID_CURSOR"
    obs.events_file.write_bytes(b"")
    assert obs.list_events(limit=2, cursor=cursor)["status"] == "CURSOR_STALE"


def test_cursor_allows_append_growth(obs):
    append_jsonl(obs.events_file, [event(i) for i in range(5)])
    first = obs.list_events(limit=2)
    with obs.events_file.open("ab") as handle:
        handle.write(json.dumps(event(99)).encode() + b"\n")
    second = obs.list_events(limit=2, cursor=first["page"]["next_cursor"])
    assert second["ok"]


@pytest.mark.parametrize("filters,expected", [
    ({"lifecycle_id": "LC-1"}, ["EV-1"]),
    ({"event_type": "ENTRY_CONFIRMED"}, ["EV-2", "EV-1"]),
    ({"status": "BLOCKED"}, ["EV-2"]),
])
def test_event_filters(obs, filters, expected):
    append_jsonl(obs.events_file, [event(1), event(2, status="BLOCKED")])
    assert [row["event_id"] for row in obs.list_events(filters)["items"]] == expected


def test_date_filters_and_unknown_filter(obs):
    append_jsonl(obs.events_file, [event(1, timestamp="2026-01-01T00:00:00+00:00"), event(2, timestamp="2026-01-03T00:00:00+00:00")])
    result = obs.list_events({"date_from": "2026-01-02T00:00:00+00:00", "date_to": "2026-01-04T00:00:00+00:00"})
    assert [row["event_id"] for row in result["items"]] == ["EV-2"]
    assert obs.list_events({"path": "x"})["status"] == "INVALID_FILTER"
    assert obs.list_events({"date_from": "2026-01-04T00:00:00+00:00", "date_to": "2026-01-01T00:00:00+00:00"})["status"] == "INVALID_FILTER"


def test_sanitization_token_headers_string_depth_collection(obs):
    manager = {
        "status": "NOOP", "token": "secret", "headers": {"Authorization": "x"},
        "warning": "x" * (module.MAX_STRING_LENGTH + 1), "reasons": list(range(150)),
        "snapshot": {"trade_id": "TR", "bot": "FALCON", "setup": "ORB", "symbol": "BTCUSDT", "side": "LONG"},
    }
    append_jsonl(obs.events_file, [event(1, manager_result=manager)])
    item = obs.list_events()["items"][0]
    assert item["summary"]["warning"].startswith("<truncated:string")
    assert len(item["summary"]["reasons"]) == 101
    assert "token" not in json.dumps(item).lower()
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}
    assert "<truncated:depth>" in json.dumps(module._sanitize(deep))


def test_noop_preserves_original_status(obs):
    append_jsonl(obs.events_file, [event(1, event_type="TRADE_UPDATED", status="BLOCKED", manager_result={"status": "NOOP", "snapshot": {"trade_id": "TR-1"}})])
    item = obs.list_events()["items"][0]
    assert item["status"] == "BLOCKED"
    assert item["summary"]["semantic_status"] == "NOOP"
    assert obs.get_metrics()["events"]["noop"] == 1


def test_external_position_is_segregated_and_bot_not_inferred(obs):
    snapshot = {"trade_id": "", "bot": "FALCON", "setup": "ORB", "symbol": "BTCUSDT", "side": "LONG", "external_position": {"manual": True}}
    append_jsonl(obs.events_file, [event(1, event_type="EXTERNAL_POSITION_DETECTED", lifecycle_id="CENTRAL-SHADOW-EXTERNAL-X", manager_result={"status": "APPLIED", "snapshot": snapshot})])
    item = obs.list_events()["items"][0]
    assert item["external_position"] is True
    assert item["bot"] is None and item["setup"] is None


def test_divergences_group_and_map_severity(obs):
    append_jsonl(obs.divergences_file, [divergence(1), divergence(2), divergence(3, field="quantity", severity="WARNING")])
    items = obs.list_divergences()["items"]
    grouped = next(item for item in items if item["field"] == "state")
    warning = next(item for item in items if item["field"] == "quantity")
    assert grouped["occurrences"] == 2
    assert grouped["severity"] == "HIGH"
    assert warning["severity"] == "MEDIUM"
    assert all(item["resolved"] is None for item in items)


def test_divergence_filters_and_external_exclusion(obs):
    append_jsonl(obs.divergences_file, [divergence(1), divergence(2, field="EXTERNAL_POSITION")])
    assert len(obs.list_divergences({"lifecycle_id": "LC-1"})["items"]) == 1
    assert obs.list_divergences({"resolved": True})["items"] == []


def test_reconciliation_no_evidence_unknown_and_sample_limit(obs):
    assert obs.get_reconciliation_summary()["status"] == "NO_EVIDENCE"
    append_jsonl(obs.divergences_file, [divergence((i % 28) + 1, field=f"field-{i}") for i in range(25)])
    result = obs.get_reconciliation_summary()
    assert result["status"] in {"DIVERGENCE", "PARTIAL"}
    assert result["matches"] is None and result["compared"] is None
    assert len(result["sample"]) <= 20


def test_provider_failures_degrade_and_no_sources_unavailable(tmp_path):
    def fail():
        raise RuntimeError("provider failed")
    degraded = TradeLifecycleShadowObservability(enabled=True, data_dir=tmp_path, adapter_health_provider=fail, lifecycle_health_provider=provider_ok)
    assert degraded.get_health()["status"] == "DEGRADED"
    unavailable = TradeLifecycleShadowObservability(enabled=True, data_dir=tmp_path)
    assert unavailable.get_health()["status"] == "UNAVAILABLE"


def test_cache_hit_miss_invalidation_and_limit(obs):
    write_json(obs.state_file, {"updated_at": datetime.now(timezone.utc).isoformat(), "metrics": {}})
    obs.get_metrics()
    first = obs._internal_snapshot()
    obs.get_metrics()
    second = obs._internal_snapshot()
    assert first["cache_misses"] >= 1
    assert second["cache_hits"] > first["cache_hits"]
    write_json(obs.state_file, {"updated_at": datetime.now(timezone.utc).isoformat(), "metrics": {"observed": 9}})
    assert obs.get_metrics()["events"]["observed"] == 9
    for index in range(200):
        obs._cache.put(str(index), {"x": index}, 10)
    assert obs._cache.count <= module.MAX_CACHE_ENTRIES


def test_metrics_are_partial_above_two_hundred_events(obs):
    append_jsonl(obs.events_file, [event(i) for i in range(205)])
    result = obs.get_metrics()
    assert result["status"] == "PARTIAL" and result["partial"] is True
    assert result["provenance"]["events"]["coverage_complete"] is False
    assert result["provenance"]["events"]["items_examined"] >= 205
    assert result["provenance"]["events"]["next_cursor"] is True


def test_metrics_are_partial_above_two_hundred_divergences(obs):
    rows = [divergence((i % 28) + 1, field=f"field-{i}") for i in range(205)]
    append_jsonl(obs.divergences_file, rows)
    result = obs.get_metrics()
    assert result["status"] == "PARTIAL" and result["partial"] is True
    assert result["provenance"]["divergences"]["coverage_complete"] is False
    assert result["provenance"]["divergences"]["next_cursor"] is True


def test_divergence_grouping_limit_and_budget_expose_partial_coverage(tmp_path):
    instance = TradeLifecycleShadowObservability(enabled=True, data_dir=tmp_path, cursor_secret=b"x", max_read_bytes=4096)
    append_jsonl(instance.divergences_file, [divergence((i % 28) + 1, field=f"field-{i}", reason="x" * 100) for i in range(80)])
    result = instance.list_divergences(limit=5)
    assert result["status"] == "PARTIAL"
    assert result["page"]["coverage_complete"] is False
    assert result["page"]["group_continuation_key"] == "divergence_id"
    assert all(item["coverage_complete"] is False and item["continuation_possible"] is True for item in result["items"])
    assert any("merge repeated divergence_id" in warning for warning in result["warnings"])


def test_unknown_severity_is_not_invented(obs):
    append_jsonl(obs.divergences_file, [divergence(1, severity="ALIEN")])
    item = obs.list_divergences()["items"][0]
    assert item["severity"] == "UNKNOWN"
    assert item["source_severity"] == "ALIEN"


@pytest.mark.parametrize("bad_provider", [
    lambda: {"ok": False, "status": "ERROR"},
    lambda: "not-a-dict",
])
def test_unhealthy_or_malformed_provider_degrades_with_other_source(tmp_path, bad_provider):
    instance = TradeLifecycleShadowObservability(enabled=True, data_dir=tmp_path, adapter_health_provider=bad_provider, lifecycle_health_provider=provider_ok)
    result = instance.get_health()
    assert result["status"] == "DEGRADED"
    assert any("adapter health provider" in warning for warning in result["warnings"])


def test_cursor_rejects_same_size_rewrite(obs):
    append_jsonl(obs.events_file, [event(i) for i in range(5)])
    first = obs.list_events(limit=2)
    cursor = first["page"]["next_cursor"]
    original = obs.events_file.read_bytes()
    obs.events_file.write_bytes(original.replace(b"EV-0", b"EV-X"))
    stat = obs.events_file.stat()
    os.utime(obs.events_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert obs.list_events(limit=2, cursor=cursor)["status"] == "CURSOR_STALE"


@pytest.mark.parametrize("field,value", [
    ("offset", "1"), ("size", "10"), ("mtime", "20"),
    ("offset", -1), ("size", -1),
])
def test_cursor_rejects_invalid_numeric_contract(obs, field, value):
    append_jsonl(obs.events_file, [event(i) for i in range(3)])
    meta = obs._file_meta(obs.events_file)
    payload = {"v": module.SCHEMA_VERSION, "source": "events", "offset": 1, "direction": "backward", "identity": meta["identity"], "size": meta["size"], "mtime": meta["mtime_ns"], "filters": obs._filter_hash({})}
    payload[field] = value
    assert obs.list_events(cursor=obs._encode_cursor(payload))["status"] == "INVALID_CURSOR"


def test_cache_is_limited_by_bytes_and_stores_only_sanitized_projection(obs):
    small = TradeLifecycleShadowObservability(enabled=True, data_dir=obs.data_dir, cursor_secret=b"small", max_cache_bytes=2048)
    for index in range(20):
        small._cache.put(str(index), {"value": "x" * 700}, 10)
    assert small._cache.bytes_used <= 2048
    manager = {"status": "APPLIED", "token": "DO-NOT-CACHE", "headers": {"Authorization": "secret"}, "snapshot": {"trade_id": "TR"}}
    append_jsonl(small.events_file, [event(1, manager_result=manager)])
    small.list_events()
    cached_text = json.dumps(list(small._cache._items.values()), default=str)
    assert "DO-NOT-CACHE" not in cached_text and "Authorization" not in cached_text


def test_response_is_bounded_to_approximately_two_mib(obs):
    large_reasons = ["x" * 4000 for _ in range(50)]
    rows = [event(i, manager_result={"status": "BLOCKED", "reasons": large_reasons, "snapshot": {"trade_id": f"TR-{i}"}}) for i in range(20)]
    append_jsonl(obs.events_file, rows)
    result = obs.list_events(limit=20)
    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= module.MAX_RESPONSE_BYTES + 32 * 1024
    assert result["status"] == "PARTIAL"


def test_health_separates_divergence_from_reconciliation_timestamp(obs):
    append_jsonl(obs.divergences_file, [divergence(1)])
    health = obs.get_health()
    assert health["last_reconciliation_at"] is None
    assert health["last_divergence_at"] == divergence(1)["timestamp"]
    summary = obs.get_reconciliation_summary()
    assert summary["known_at"] is None
    assert summary["last_divergence_at"] == divergence(1)["timestamp"]


def test_unreadable_source_and_exceptions_fail_open_without_writes(tmp_path, monkeypatch):
    events_directory = tmp_path / "trade_lifecycle_shadow_runtime_events.jsonl"
    events_directory.mkdir()
    instance = TradeLifecycleShadowObservability(enabled=True, data_dir=tmp_path, adapter_health_provider=provider_ok, lifecycle_health_provider=provider_ok)
    before = sorted(path.name for path in tmp_path.iterdir())
    assert instance.list_events()["status"] == "UNAVAILABLE"
    monkeypatch.setattr(instance, "_file_meta", lambda path: (_ for _ in ()).throw(PermissionError("denied")))
    for call in (instance.get_health, instance.get_metrics, instance.list_events, instance.list_divergences, instance.get_reconciliation_summary):
        assert isinstance(call(), dict)
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_concurrent_readers_and_append(obs):
    append_jsonl(obs.events_file, [event(i) for i in range(20)])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: obs.list_events(limit=5), range(32)))
    assert all(result["ok"] and len(result["items"]) == 5 for result in results)
    initial_size = obs.events_file.stat().st_size
    with obs.events_file.open("ab") as handle:
        handle.write(json.dumps(event(99)).encode() + b"\n")
    assert obs.events_file.stat().st_size > initial_size
    assert obs.list_events(limit=1)["items"][0]["event_id"] == "EV-99"


def test_state_replace_is_tolerated(obs):
    write_json(obs.state_file, {"updated_at": datetime.now(timezone.utc).isoformat(), "metrics": {"observed": 1}})
    replacement = obs.state_file.with_suffix(".replacement")
    write_json(replacement, {"updated_at": datetime.now(timezone.utc).isoformat(), "metrics": {"observed": 2}})
    os.replace(replacement, obs.state_file)
    assert obs.get_metrics()["events"]["observed"] == 2


def test_no_writes_or_file_creation(tmp_path):
    obs = TradeLifecycleShadowObservability(enabled=True, data_dir=tmp_path, adapter_health_provider=provider_ok, lifecycle_health_provider=provider_ok)
    before = list(tmp_path.iterdir())
    obs.get_health(); obs.get_metrics(); obs.list_events(); obs.list_divergences(); obs.get_reconciliation_summary()
    assert list(tmp_path.iterdir()) == before == []


def test_no_network(monkeypatch, obs):
    def forbidden(*args, **kwargs):
        raise AssertionError("network attempted")
    monkeypatch.setattr(socket, "socket", forbidden)
    assert obs.get_health()["status"] in {"OK", "DEGRADED"}
    assert obs.list_events()["ok"]


def test_source_prohibitions():
    source_path = Path(module.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"broker", "main", "requests", "httpx", "aiohttp", "trade_registry", "trade_lifecycle_manager", "trade_lifecycle_shadow_runtime_adapter"}
    for forbidden in ("reconcile_all(", "compare_with_registry(", "os.replace(", ".unlink(", ".rename(", ".truncate(", ".mkdir("):
        assert forbidden not in source
    assert 'open("w"' not in source and 'open("a"' not in source and 'open("ab"' not in source


def test_public_exceptions_do_not_escape(obs, monkeypatch):
    monkeypatch.setattr(obs, "_file_meta", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    calls = [obs.get_health, obs.get_metrics, obs.list_events, obs.list_divergences, obs.get_reconciliation_summary]
    results = [call() for call in calls]
    assert all(isinstance(result, dict) for result in results)
    assert obs._internal_snapshot()["request_errors"] >= 5


def test_internal_metrics_are_separate(obs):
    result = obs.get_metrics()
    assert "observability_internal" in result
    assert "requests" not in result["events"]
    assert result["observability_internal"] is not result["events"]


def test_public_module_wrappers_are_disabled_safely():
    for result in (module.get_health(), module.get_metrics(), module.list_events(), module.list_divergences(), module.get_reconciliation_summary()):
        assert result["status"] == "DISABLED"
        assert result["operational_authority"] is False
