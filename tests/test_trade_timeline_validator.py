from __future__ import annotations

import copy
import json
import socket

import pytest

import trade_timeline_validator as validator_module
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
    valid = [json.dumps(event(name, index + 1)) for index, name in enumerate(REQUIRED_EVENTS)]
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
