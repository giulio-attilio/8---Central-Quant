from __future__ import annotations

import copy
import json
import socket

import pytest

import trade_timeline_validator as validator_module
from trade_timeline_validator import COMPONENTS, REQUIRED_EVENTS, validate_trade_timeline


TRADE_ID = "TR-LIVE-1"
SHADOW_VALIDATED_BASE_FIELDS = ["trade_id", "bot", "setup", "symbol", "side", "mode", "status"]
SHADOW_VALIDATED_LIVE_CLOSED_FIELDS = SHADOW_VALIDATED_BASE_FIELDS + [
    "quantity_open", "client_order_id", "exchange_order_id",
]
SHADOW_VALIDATED_LIVE_OPEN_FIELDS = SHADOW_VALIDATED_LIVE_CLOSED_FIELDS + [
    "protection", "disaster_stop_order_id",
]


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
        "broker": [event("BROKER_ACK", 5, ok=True, sent=True, status="SENT", order_id="ORDER-1", position_status="CLOSED", symbol="BTCUSDT", side="LONG", entry_price=100.0, exit_price=110.0, quantity=1.0), event("LIVE_TRADE_CLOSED", 10)],
        "shadow_runtime": [event(
            "SHADOW_VALIDATED", 13, status="MATCH", operational_authority=False,
            shadow_mode=True, source_component="TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
            compared_fields=10, matching_fields=10, differences=[], symbol="BTCUSDT",
            side="LONG", entry=100.0, exit_price=110.0, quantity=1.0,
            mode="LIVE", registry_status="CLOSED",
            validated_fields=SHADOW_VALIDATED_LIVE_CLOSED_FIELDS,
        )],
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


def _write_jsonl_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b""
    for line in lines:
        encoded = line if isinstance(line, bytes) else str(line).encode("utf-8")
        payload += encoded + (b"" if encoded.endswith(b"\n") else b"\n")
    path.write_bytes(payload)
    return payload


def _validate_from_data_dir(tmp_path, monkeypatch, trade_id=TRADE_ID):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    return validate_trade_timeline(trade_id)


@pytest.mark.parametrize(
    "lines,invalid_count",
    [
        (["{broken-before", json.dumps(event("POSITION_OPEN", 6))], 1),
        ([json.dumps(event("POSITION_OPEN", 6)), "{broken-after"], 1),
        (["{bad-1", json.dumps(event("POSITION_OPEN", 6)), "{bad-2", "not-json"], 3),
    ],
)
def test_invalid_jsonl_lines_are_skipped_around_valid_evidence(tmp_path, monkeypatch, lines, invalid_count):
    _write_jsonl_lines(tmp_path / "timeline.jsonl", lines)

    report = _validate_from_data_dir(tmp_path, monkeypatch)

    component = report["components"]["timeline"]
    assert component["status"] == "AVAILABLE"
    assert component["records"] == 1
    assert component["invalid_lines"] == invalid_count
    assert component["valid_lines"] == 1
    warning = next(item for item in report["warnings"] if item["component"] == "timeline")
    assert warning == {"component": "timeline", "code": "CORRUPT_JSONL_LINES_SKIPPED", "count": invalid_count}


def test_truncated_last_jsonl_line_is_counted_and_does_not_hide_valid_evidence(tmp_path, monkeypatch):
    path = tmp_path / "timeline.jsonl"
    valid = json.dumps(event("POSITION_OPEN", 6)).encode("utf-8") + b"\n"
    truncated = b'{"trade_id":"TR-LIVE-1","event_type":"BROKER_ACK"'
    path.write_bytes(valid + truncated)

    report = _validate_from_data_dir(tmp_path, monkeypatch)

    assert report["components"]["timeline"]["status"] == "AVAILABLE"
    assert report["components"]["timeline"]["invalid_lines"] == 1
    assert any(item["event"] == "POSITION_OPEN" for item in report["events_found"])


def test_file_with_only_invalid_nonempty_lines_is_degraded_without_raw_content(tmp_path, monkeypatch):
    corrupt_secret = "{CORRUPT-RAW-SECRET-DO-NOT-EXPOSE"
    _write_jsonl_lines(tmp_path / "history_events.jsonl", [corrupt_secret, "not-json-either"])

    report = _validate_from_data_dir(tmp_path, monkeypatch, trade_id="UNKNOWN-TRADE")

    component = report["components"]["history_manager"]
    assert component["status"] == "DEGRADED"
    assert component["invalid_lines"] == 2
    assert component["valid_lines"] == 0
    assert component["lines_scanned"] == 2
    assert corrupt_secret not in json.dumps(report, ensure_ascii=False)
    assert not any(item.get("component") == "history_manager" for item in report["errors"])


def test_empty_lines_are_ignored_without_becoming_corruption(tmp_path, monkeypatch):
    (tmp_path / "history_events.jsonl").write_bytes(b"\n  \n\r\n")

    report = _validate_from_data_dir(tmp_path, monkeypatch, trade_id="UNKNOWN-TRADE")

    component = report["components"]["history_manager"]
    assert component["status"] == "NO_EVIDENCE"
    assert component["lines_scanned"] == 3
    assert component["valid_lines"] == 0
    assert component["invalid_lines"] == 0
    assert not any(item.get("component") == "history_manager" for item in report["warnings"])


def test_unknown_trade_with_invalid_and_valid_unrelated_line_is_no_evidence(tmp_path, monkeypatch):
    unrelated = event("SIGNAL_RECEIVED", 1, trade_id="OTHER-TRADE")
    _write_jsonl_lines(tmp_path / "history_events.jsonl", ["{bad", json.dumps(unrelated)])

    report = _validate_from_data_dir(tmp_path, monkeypatch, trade_id="UNKNOWN-TRADE")

    component = report["components"]["history_manager"]
    assert component["status"] == "NO_EVIDENCE"
    assert component["invalid_lines"] == 1
    assert component["valid_lines"] == 1
    assert any(item == {"component": "history_manager", "code": "CORRUPT_JSONL_LINES_SKIPPED", "count": 1} for item in report["warnings"])


def test_complete_trade_with_corrupt_line_still_passes(tmp_path, monkeypatch):
    valid = []
    for index, name in enumerate(REQUIRED_EVENTS):
        updates = {}
        if name == "BROKER_ACK":
            updates = {"ok": True, "sent": True, "status": "SENT", "order_id": "ORDER-CORRUPT-TEST"}
        elif name == "SHADOW_VALIDATED":
            updates = {
                "status": "MATCH", "operational_authority": False, "shadow_mode": True,
                "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
                "compared_fields": 10, "matching_fields": 10, "differences": [],
                "mode": "LIVE", "registry_status": "CLOSED",
                "validated_fields": SHADOW_VALIDATED_LIVE_CLOSED_FIELDS,
            }
        valid.append(json.dumps(event(name, index + 1, **updates)))
    _write_jsonl_lines(tmp_path / "timeline.jsonl", [valid[0], "{corrupt-middle", *valid[1:]])

    report = _validate_from_data_dir(tmp_path, monkeypatch)

    assert report["result"] == "PASS"
    assert report["events_missing"] == []
    assert report["components"]["timeline"]["status"] == "AVAILABLE"
    assert report["components"]["timeline"]["invalid_lines"] == 1
    assert report["warnings"] == [{"component": "timeline", "code": "CORRUPT_JSONL_LINES_SKIPPED", "count": 1}]


def test_production_regression_invalid_history_and_timeline_do_not_become_error(tmp_path, monkeypatch):
    unrelated = json.dumps(event("SIGNAL_RECEIVED", 1, trade_id="OTHER-TRADE"))
    _write_jsonl_lines(tmp_path / "history_events.jsonl", ["{bad-history", unrelated])
    _write_jsonl_lines(tmp_path / "timeline.jsonl", ["{bad-timeline", unrelated])

    report = _validate_from_data_dir(tmp_path, monkeypatch, trade_id="TESTE_INEXISTENTE_001")

    assert report["result"] == "FAIL"
    assert report["components"]["history_manager"]["status"] == "NO_EVIDENCE"
    assert report["components"]["timeline"]["status"] == "NO_EVIDENCE"
    assert {item["component"] for item in report["warnings"]} == {"history_manager", "timeline"}
    assert not any(item.get("component") in {"history_manager", "timeline"} for item in report["errors"])
    assert report["fail_open"] is True
    assert report["production_blocked"] is False


def test_permission_error_remains_source_error(tmp_path, monkeypatch):
    target = tmp_path / "history_events.jsonl"
    target.write_text(json.dumps(event("SIGNAL_RECEIVED", 1)), encoding="utf-8")
    original_open = validator_module.Path.open

    def denied(path, *args, **kwargs):
        if path == target:
            raise PermissionError("denied for test")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(validator_module.Path, "open", denied)
    report = _validate_from_data_dir(tmp_path, monkeypatch)

    assert report["components"]["history_manager"]["status"] == "ERROR"
    assert report["components"]["history_manager"]["error_type"] == "PermissionError"
    assert any(item["component"] == "history_manager" and item["error_type"] == "PermissionError" for item in report["errors"])


def test_jsonl_reader_limits_bytes_and_valid_lines_with_partial_coverage(tmp_path, monkeypatch):
    rows = [json.dumps(event("TRAILING_UPDATED", index + 1, event_id=f"LIMIT-{index}")) for index in range(8)]
    original = _write_jsonl_lines(tmp_path / "timeline.jsonl", rows)
    monkeypatch.setattr(validator_module, "JSONL_MAX_VALID_LINES", 2)
    monkeypatch.setattr(validator_module, "JSONL_MAX_BYTES", len(original))

    report = _validate_from_data_dir(tmp_path, monkeypatch)

    component = report["components"]["timeline"]
    assert component["valid_lines"] == 2
    assert component["records"] == 2
    assert component["partial"] is True
    assert component["coverage_limited"] is True
    assert component["bytes_scanned"] < len(original)


def test_corrupt_jsonl_read_is_read_only_and_has_no_network_or_broker_import(tmp_path, monkeypatch):
    path = tmp_path / "timeline.jsonl"
    original = _write_jsonl_lines(path, ["{bad", json.dumps(event("POSITION_OPEN", 6))])
    broker_before = __import__("sys").modules.get("broker")
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: pytest.fail("network access"))

    report = _validate_from_data_dir(tmp_path, monkeypatch)

    assert report["components"]["timeline"]["invalid_lines"] == 1
    assert path.read_bytes() == original
    assert __import__("sys").modules.get("broker") is broker_before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["timeline.jsonl"]


def _falcon_registry(**updates):
    row = {
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "mode": "LIVE",
        "status": "OPEN",
        "opened_at": "2026-07-14T11:00:18Z",
        "qty": 0.12,
        "remaining_quantity": 0.12,
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "broker_order_id": "2077030442691940352",
        "metadata": {
            "broker_stop_order_id": "2077030444402577408",
            "partial_capable_sizing": {
                "market_limits": {"precision": {"amount": 0.01}, "amount_precision": 0.01}
            },
        },
    }
    row.update(updates)
    return row


def _falcon_sources(**updates):
    sources = {name: [] for name in COMPONENTS}
    sources["registry"] = [_falcon_registry()]
    sources["timeline"] = [
        {
            "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT",
            "event_type": "SIGNAL_RECEIVED",
            "timestamp": "2026-07-14T11:00:19Z",
            "event_id": "FALCON-SIGNAL",
        },
    ]
    sources.update(updates)
    return sources


def _found(report):
    return [item["event"] for item in report["events_found"]]


def test_registry_precision_amount_never_replaces_authoritative_quantity():
    sources = _falcon_sources(
        broker=[{
            "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
            "symbol": "SOL/USDT:USDT",
            "position_side": "SHORT",
            "position_found": True,
            "position_status": "OPEN",
            "contracts": 0.12,
        }]
    )
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=sources)
    assert not any(item["field"] in {"quantity", "symbol", "side"} for item in report["divergences"])


def test_amount_precision_is_not_a_trade_quantity():
    registry = _falcon_registry()
    registry["metadata"]["amount_precision"] = 0.01
    sources = _falcon_sources(
        registry=[registry],
        broker=[{"broker_order_id": "2077030442691940352", "position_found": True, "position_status": "OPEN", "contracts": 0.12}],
    )
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=sources)
    assert not any(item["field"] == "quantity" for item in report["divergences"])


def test_registry_initial_quantity_alias_precedes_secondary_root_quantity():
    registry = _falcon_registry(quantity=0.01)
    registry.pop("remaining_quantity")
    registry.pop("qty")
    registry["metadata"]["initial_quantity"] = 0.12
    sources = _falcon_sources(
        registry=[registry],
        broker=[{
            "broker_order_id": "2077030442691940352",
            "position_found": True,
            "position_status": "OPEN",
            "contracts": 0.12,
        }],
    )
    report = validate_trade_timeline(registry["trade_id"], sources=sources)
    assert not any(item["field"] == "quantity" for item in report["divergences"])


def test_decision_allow_live_persisted_in_registry_maps_to_risk_approved():
    registry = _falcon_registry()
    registry["metadata"]["execution_decision"] = {"allowed": True, "decision": "ALLOW", "mode": "LIVE"}
    report = validate_trade_timeline(registry["trade_id"], sources=_falcon_sources(registry=[registry]))
    assert "RISK_APPROVED" in _found(report)


def test_registry_persistence_timestamp_is_not_used_as_risk_decision_time():
    registry = _falcon_registry(opened_at="2026-07-14T11:00:30Z")
    registry["metadata"]["execution_decision"] = {"allowed": True, "decision": "ALLOW", "mode": "LIVE"}
    sent = {
        "event": "place_market_order", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "timestamp": "2026-07-14T11:00:20Z",
    }
    report = validate_trade_timeline(
        registry["trade_id"],
        sources=_falcon_sources(registry=[registry], broker=[sent]),
    )
    risk = next(item for item in report["events_found"] if item["raw_event"] == "DECISION_ALLOW_LIVE")
    assert risk["timestamp"] is None
    assert report["chronology"]["ordered"] is True


def test_explicit_decision_timestamp_is_preserved_for_derived_risk_event():
    registry = _falcon_registry(opened_at="2026-07-14T11:00:30Z")
    registry["metadata"]["execution_decision"] = {
        "allowed": True, "decision": "ALLOW", "mode": "LIVE",
        "occurred_at": "2026-07-14T11:00:19Z",
    }
    report = validate_trade_timeline(registry["trade_id"], sources=_falcon_sources(registry=[registry]))
    risk = next(item for item in report["events_found"] if item["raw_event"] == "DECISION_ALLOW_LIVE")
    assert risk["timestamp"] == "2026-07-14T11:00:19+00:00"


def test_real_place_market_order_maps_to_execution_requested_only_with_send_evidence():
    row = {
        "event": "place_market_order", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "symbol": "SOL-USDT", "position_side": "SHORT", "timestamp": "2026-07-14T11:00:20Z",
    }
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(broker=[row]))
    assert {"EXECUTION_REQUESTED", "LIVE_ORDER_SENT", "BROKER_ACK"}.issubset(_found(report))


def test_broker_live_sent_maps_to_live_order_sent_and_ack():
    row = {
        "event": "BROKER_LIVE_SENT", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "symbol": "SOLUSDT", "position_side": "SHORT", "timestamp": "2026-07-14T11:00:21Z",
    }
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(broker=[row]))
    assert {"LIVE_ORDER_SENT", "BROKER_ACK"}.issubset(_found(report))


@pytest.mark.parametrize("event_name", ["place_market_order", "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED"])
def test_order_sent_before_disaster_stop_failure_still_maps_to_send_and_ack(event_name):
    row = {
        "event": event_name,
        "ok": False,
        "sent": True,
        "status": "LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "order_id": "2077030442691940352",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "timestamp": "2026-07-14T11:00:21Z",
    }
    report = validate_trade_timeline(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_falcon_sources(broker=[row]),
    )
    assert {"LIVE_ORDER_SENT", "BROKER_ACK"}.issubset(_found(report))
    assert "POSITION_OPEN" in _found(report)


def test_place_and_critical_stop_failure_audit_are_one_canonical_send():
    base = {
        "ok": False, "sent": True, "status": "LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "order_id": "2077030442691940352",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
    }
    rows = [
        {**base, "event": "place_market_order", "timestamp": "2026-07-14T11:00:20Z"},
        {**base, "event": "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED", "timestamp": "2026-07-14T11:00:21Z"},
    ]
    report = validate_trade_timeline(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_falcon_sources(broker=rows),
    )
    assert sum(item["event"] == "LIVE_ORDER_SENT" for item in report["events_found"]) == 1
    assert sum(item["event"] == "BROKER_ACK" for item in report["events_found"]) == 1
    assert not any(item["event"] in {"LIVE_ORDER_SENT", "BROKER_ACK"} for item in report["events_duplicated"])


def test_current_open_trade_recognizes_complete_canonical_prefix():
    registry = _falcon_registry()
    registry["metadata"]["execution_decision"] = {"allowed": True, "decision": "ALLOW", "mode": "LIVE"}
    requested = {
        "event": "place_market_order", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "symbol": "SOLUSDT", "position_side": "SHORT", "timestamp": "2026-07-14T11:00:20Z",
    }
    sent = {**requested, "event": "BROKER_LIVE_SENT", "timestamp": "2026-07-14T11:00:21Z"}
    timeline = [
        {"trade_id": registry["trade_id"], "event_type": "SIGNAL_RECEIVED", "timestamp": "2026-07-14T11:00:19Z"},
        {"trade_id": registry["trade_id"], "event_type": "POSITION_OPEN", "timestamp": "2026-07-14T11:00:22Z"},
    ]
    report = validate_trade_timeline(
        registry["trade_id"],
        sources=_falcon_sources(registry=[registry], broker=[requested, sent], timeline=timeline),
    )
    assert {
        "SIGNAL_RECEIVED", "RISK_APPROVED", "EXECUTION_REQUESTED",
        "LIVE_ORDER_SENT", "BROKER_ACK", "POSITION_OPEN",
    }.issubset(_found(report))
    assert not any(item["event"] in {"LIVE_ORDER_SENT", "BROKER_ACK"} for item in report["events_duplicated"])
    assert {"LIVE_TRADE_CLOSED", "REGISTRY_CLOSE", "LIFECYCLE_FINISHED"}.issubset(report["events_missing"])


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "PREVIEW", "sent": False, "order_id": None},
        {"status": "SENT", "sent": False},
        {"status": "SENT", "sent": True, "order_id": None},
        {"status": "SENT", "sent": True, "ok": False},
    ],
)
def test_preview_or_insufficient_broker_evidence_never_becomes_ack(updates):
    row = {
        "event": "BROKER_LIVE_SENT", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
    }
    row.update(updates)
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(broker=[row]))
    assert "BROKER_ACK" not in _found(report)


def test_shadow_validated_requires_explicit_match_without_differences():
    matched = {
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT", "event_type": "SHADOW_VALIDATED",
        "status": "MATCH", "differences": [], "operational_authority": False,
        "shadow_mode": True, "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
        "compared_fields": 12, "matching_fields": 12,
        "mode": "LIVE", "registry_status": "OPEN",
        "validated_fields": SHADOW_VALIDATED_LIVE_OPEN_FIELDS,
        "timestamp": "2026-07-14T11:00:30Z", "event_id": "SV-1",
    }
    report = validate_trade_timeline(matched["trade_id"], sources=_falcon_sources(shadow_runtime=[matched]))
    assert "SHADOW_VALIDATED" in _found(report)


@pytest.mark.parametrize(
    "row",
    [
        {"event_type": "TRADE_UPDATED", "status": "APPLIED", "manager_result": {"status": "EVENT_APPLIED"}},
        {"event_type": "SHADOW_VALIDATED", "status": "DIVERGENCE", "differences": [{"field": "quantity"}]},
        {"event_type": "SHADOW_VALIDATED", "status": "PARTIAL_MATCH", "differences": []},
        {"event_type": "SHADOW_VALIDATED", "status": "MATCH", "differences": [], "operational_authority": False},
        {"event_type": "SHADOW_VALIDATED", "status": "MATCH", "differences": [], "operational_authority": False, "shadow_mode": True, "source_component": "UNTRUSTED", "compared_fields": 8, "matching_fields": 8},
        {"event_type": "SHADOW_VALIDATED", "status": "MATCH", "differences": [], "operational_authority": False, "shadow_mode": True, "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER", "compared_fields": 8, "matching_fields": 7},
    ],
)
def test_applied_or_divergent_shadow_record_is_not_validation(row):
    row = {"trade_id": "FALCON:FALCON15:SOLUSDT:SHORT", "timestamp": "2026-07-14T11:00:30Z", **row}
    report = validate_trade_timeline(row["trade_id"], sources=_falcon_sources(shadow_runtime=[row]))
    assert "SHADOW_VALIDATED" not in _found(report)


def test_shadow_validation_is_meta_event_and_does_not_break_chronology():
    sources = valid_sources()
    sources["shadow_runtime"] = [
        event("SHADOW_VALIDATED", 5, status="MATCH", differences=[], operational_authority=False, shadow_mode=True, source_component="TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER", compared_fields=10, matching_fields=10, mode="LIVE", registry_status="CLOSED", validated_fields=SHADOW_VALIDATED_LIVE_CLOSED_FIELDS, event_id="SV-A"),
        event("SHADOW_VALIDATED", 9, status="MATCH", differences=[], operational_authority=False, shadow_mode=True, source_component="TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER", compared_fields=10, matching_fields=10, mode="LIVE", registry_status="CLOSED", validated_fields=SHADOW_VALIDATED_LIVE_CLOSED_FIELDS, event_id="SV-B"),
    ]
    report = validate_trade_timeline(TRADE_ID, sources=sources)
    assert report["chronology"]["ordered"] is True
    assert not any(item["event"] == "SHADOW_VALIDATED" for item in report["events_duplicated"])


def test_turtle_vet_close_cannot_match_falcon_through_truncated_stop_client_id():
    turtle = {
        "trade_id": "TURTLE55:VETUSDT:LONG", "bot": "TURTLE", "setup": "TURTLE55",
        "symbol": "VETUSDT", "side": "LONG", "client_order_id": "FALCON-LIVE-FALCON15-178-DS",
        "event_type": "LIVE_TRADE_CLOSED", "event_id": "TURTLE55:VETUSDT:LONG",
        "timestamp": "2026-07-12T12:00:00Z",
    }
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(timeline=[turtle]))
    assert "LIVE_TRADE_CLOSED" not in _found(report)
    assert report["components"]["timeline"]["records"] == 0


def test_truncated_ds_id_alone_never_establishes_timeline_ownership():
    ambiguous = {
        "client_order_id": "FALCON-LIVE-FALCON15-178-DS", "event_type": "LIVE_TRADE_CLOSED",
        "timestamp": "2026-07-14T11:10:00Z",
    }
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(timeline=[ambiguous]))
    assert report["components"]["timeline"]["records"] == 0


def test_same_symbol_and_side_different_bot_is_rejected_after_id_candidate():
    foreign = {
        "broker_order_id": "2077030442691940352", "bot": "DONKEY", "symbol": "SOLUSDT",
        "side": "SHORT", "event_type": "POSITION_OPEN", "timestamp": "2026-07-14T11:01:00Z",
    }
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(timeline=[foreign]))
    assert report["components"]["timeline"]["records"] == 0


@pytest.mark.parametrize("identity_key", ["registry_id", "trade_uuid"])
def test_conflicting_typed_trade_identity_rejects_matching_order_id(identity_key):
    registry = _falcon_registry(**{identity_key: "CENTRAL-TRADE-A"})
    candidate = {
        identity_key: "CENTRAL-TRADE-B",
        "broker_order_id": "2077030442691940352",
        "event_type": "POSITION_OPEN",
        "timestamp": "2026-07-14T11:01:00Z",
    }
    report = validate_trade_timeline(
        registry["trade_id"],
        sources=_falcon_sources(registry=[registry], timeline=[candidate]),
    )
    assert report["components"]["timeline"]["records"] == 0


@pytest.mark.parametrize("identity_key", ["registry_id", "trade_uuid"])
def test_matching_typed_trade_identity_accepts_matching_order_id(identity_key):
    registry = _falcon_registry(**{identity_key: "CENTRAL-TRADE-A"})
    candidate = {
        identity_key: "CENTRAL-TRADE-A",
        "broker_order_id": "2077030442691940352",
        "event_type": "POSITION_OPEN",
        "timestamp": "2026-07-14T11:01:00Z",
    }
    report = validate_trade_timeline(
        registry["trade_id"],
        sources=_falcon_sources(registry=[registry], timeline=[candidate]),
    )
    assert report["components"]["timeline"]["records"] == 1


@pytest.mark.parametrize(
    "registry_key,candidate_key",
    [("trade_uuid", "registry_id"), ("registry_id", "trade_uuid")],
)
def test_equal_text_across_different_identity_types_does_not_establish_ownership(registry_key, candidate_key):
    registry = _falcon_registry(**{registry_key: "SAME-TEXT-DIFFERENT-TYPE"})
    candidate = {
        candidate_key: "SAME-TEXT-DIFFERENT-TYPE",
        "event_type": "POSITION_OPEN",
        "timestamp": "2026-07-14T11:01:00Z",
    }
    report = validate_trade_timeline(
        registry["trade_id"],
        sources=_falcon_sources(registry=[registry], timeline=[candidate]),
    )
    assert report["components"]["timeline"]["records"] == 0


def test_same_structural_trade_on_older_date_is_not_merged():
    old = {
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT", "bot": "FALCON", "setup": "FALCON15",
        "symbol": "SOLUSDT", "side": "SHORT", "event_type": "LIVE_TRADE_CLOSED",
        "timestamp": "2026-07-10T12:00:00Z", "client_order_id": "FALCON-LIVE-FALCON15-OLD",
    }
    report = validate_trade_timeline(old["trade_id"], sources=_falcon_sources(timeline=[old]))
    assert report["components"]["timeline"]["records"] == 0


def test_same_logical_trade_with_another_client_id_nearby_is_not_merged():
    other_execution = {
        "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT", "bot": "FALCON", "setup": "FALCON15",
        "symbol": "SOLUSDT", "side": "SHORT", "event_type": "LIVE_TRADE_CLOSED",
        "timestamp": "2026-07-14T10:30:18Z", "client_order_id": "FALCON-LIVE-FALCON15-OTHER",
    }
    report = validate_trade_timeline(other_execution["trade_id"], sources=_falcon_sources(timeline=[other_execution]))
    assert report["components"]["timeline"]["records"] == 0


def test_broker_symbol_alias_and_position_side_are_consistency_checks_only():
    broker = {
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618", "symbol": "SOL/USDT:USDT",
        "side": "BUY", "position_side": "SHORT", "position_found": True,
        "position_status": "OPEN", "contracts": 0.12, "timestamp": "2026-07-14T11:00:22Z",
    }
    report = validate_trade_timeline("FALCON:FALCON15:SOLUSDT:SHORT", sources=_falcon_sources(broker=[broker]))
    assert report["components"]["broker"]["records"] == 1
    assert not any(item["field"] in {"symbol", "side"} for item in report["divergences"])


def test_stop_quantity_alias_does_not_replace_broker_position_quantity():
    position = {
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618", "symbol": "SOLUSDT",
        "position_side": "SHORT", "position_found": True, "position_status": "OPEN", "contracts": 0.12,
    }
    stop = {
        "event": "BROKER_DISASTER_STOP_CREATED", "order_id": "2077030444402577408",
        "client_order_id": "FALCON-LIVE-FALCON15-178-DS", "quantity": 0.01,
        "symbol": "SOLUSDT", "position_side": "SHORT", "timestamp": "2026-07-14T11:00:22Z",
    }
    report = validate_trade_timeline(
        "FALCON:FALCON15:SOLUSDT:SHORT",
        sources=_falcon_sources(broker=[position, stop]),
    )
    assert not any(item["field"] == "quantity" for item in report["divergences"])


def test_initial_broker_send_amount_is_not_current_quantity_after_partial_close():
    registry = _falcon_registry(remaining_quantity=0.06)
    sent = {
        "event": "BROKER_LIVE_SENT", "ok": True, "sent": True, "status": "SENT",
        "order_id": "2077030442691940352", "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "amount": 0.12, "symbol": "SOLUSDT", "position_side": "SHORT",
    }
    partial = {
        "trade_id": registry["trade_id"], "event": "CLOSE_PARTIAL_RECORDED",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618", "timestamp": "2026-07-14T11:05:00Z",
    }
    report = validate_trade_timeline(
        registry["trade_id"],
        sources=_falcon_sources(registry=[registry], broker=[sent, partial]),
    )
    assert not any(item["field"] == "quantity" for item in report["divergences"])


def test_shadow_paths_follow_dedicated_shadow_data_dir(tmp_path, monkeypatch):
    central = tmp_path / "central"
    shadow = tmp_path / "shadow"
    central.mkdir()
    shadow.mkdir()
    registry = _falcon_registry()
    (central / "trade_registry.json").write_text(json.dumps({"open_trades": {registry["trade_id"]: registry}, "closed_trades": []}), encoding="utf-8")
    shadow_event = {
        "trade_id": registry["trade_id"], "event_type": "SHADOW_VALIDATED", "status": "MATCH",
        "differences": [], "operational_authority": False, "shadow_mode": True,
        "source_component": "TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER",
        "compared_fields": 12, "matching_fields": 12, "timestamp": "2026-07-14T11:01:00Z",
        "mode": "LIVE", "registry_status": "OPEN",
        "validated_fields": SHADOW_VALIDATED_LIVE_OPEN_FIELDS,
    }
    (shadow / "trade_lifecycle_shadow_runtime_events.jsonl").write_text(json.dumps(shadow_event) + "\n", encoding="utf-8")
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(central))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(shadow))
    report = validate_trade_timeline(registry["trade_id"])
    assert report["components"]["shadow_runtime"]["records"] == 1
    assert "SHADOW_VALIDATED" in _found(report)
