from __future__ import annotations

import ast
import copy
import socket
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))


class LoggerProbe:
    def __init__(self):
        self.calls = []

    def exception(self, message, *args):
        self.calls.append((message, args))


def _route_function_node():
    node = next(
        item
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "trade_timeline_validator_v1_route"
    )
    return copy.deepcopy(node)


def _compile_route(args):
    node = _route_function_node()
    node.decorator_list = []
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    logger = LoggerProbe()
    namespace = {
        "request": SimpleNamespace(args=args),
        "app": SimpleNamespace(logger=logger),
        "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
    }
    exec(compile(tree, "<isolated-trade-timeline-route>", "exec"), namespace)
    return namespace["trade_timeline_validator_v1_route"], logger


def _install_validator(monkeypatch, result=None, error=None):
    calls = []

    def validate(trade_id):
        calls.append(trade_id)
        if error is not None:
            raise error
        return result

    monkeypatch.setitem(
        sys.modules,
        "trade_timeline_validator",
        SimpleNamespace(validate_trade_timeline=validate),
    )
    return calls


def _report(result="PASS"):
    return {
        "ok": True,
        "result": result,
        "valid": result == "PASS",
        "fail_open": True,
        "production_blocked": False,
        "generated_at": "2026-07-13T12:00:00+00:00",
        "components": {"registry": {"status": "AVAILABLE"}},
        "events_found": [{"event": "SIGNAL_RECEIVED"}],
        "events_missing": [] if result == "PASS" else ["BROKER_ACK"],
        "events_duplicated": [],
        "divergences": [],
        "latencies": [{"from": "SIGNAL_RECEIVED", "to": "RISK_APPROVED", "latency_ms": 10}],
        "warnings": [],
        "errors": [],
    }


def test_route_is_registered_as_manual_get_only():
    decorators = [ast.unparse(item) for item in _route_function_node().decorator_list]
    assert decorators == ["app.route('/trade_timeline', methods=['GET'])"]


def test_missing_trade_id_returns_400_without_loading_validator():
    validator_before = sys.modules.get("trade_timeline_validator")
    route, _ = _compile_route({})
    payload, status = route()
    assert status == 400
    assert payload["error"] == "TRADE_ID_REQUIRED"
    assert sys.modules.get("trade_timeline_validator") is validator_before


def test_empty_trade_id_returns_400():
    route, _ = _compile_route({"trade_id": "   "})
    payload, status = route()
    assert status == 400
    assert payload["error"] == "TRADE_ID_REQUIRED"


def test_valid_trade_id_is_trimmed_and_pass_contract_is_projected(monkeypatch):
    route, _ = _compile_route({"trade_id": "  TR-123  "})
    calls = _install_validator(monkeypatch, _report("PASS"))
    payload, status = route()
    assert status == 200
    assert calls == ["TR-123"]
    assert payload == {
        "ok": True,
        "trade_id": "TR-123",
        "validation_status": "PASS",
        "pass": True,
        "fail_open": True,
        "production_blocked": False,
        "generated_at": "2026-07-13T12:00:00+00:00",
        "component_status": {"registry": "AVAILABLE"},
        "events_found": [{"event": "SIGNAL_RECEIVED"}],
        "missing_events": [],
        "duplicate_events": [],
        "divergences": [],
        "latencies": [{"from": "SIGNAL_RECEIVED", "to": "RISK_APPROVED", "latency_ms": 10}],
        "warnings": [],
        "errors": [],
    }


def test_logical_fail_returns_http_200(monkeypatch):
    route, _ = _compile_route({"trade_id": "TR-FAIL"})
    _install_validator(monkeypatch, _report("FAIL"))
    payload, status = route()
    assert status == 200
    assert payload["validation_status"] == "FAIL"
    assert payload["pass"] is False
    assert payload["missing_events"] == ["BROKER_ACK"]
    assert payload["production_blocked"] is False


def test_unexpected_route_error_is_sanitized_500(monkeypatch):
    route, logger = _compile_route({"trade_id": "TR-ERROR"})
    _install_validator(monkeypatch, error=RuntimeError("private C:/secret/path"))
    payload, status = route()
    assert status == 500
    assert payload["errors"] == [{"code": "TRADE_TIMELINE_ROUTE_INTERNAL_ERROR"}]
    assert "secret" not in str(payload)
    assert logger.calls


def test_trade_id_length_and_file_paths_are_rejected():
    for trade_id, error in (("X" * 257, "TRADE_ID_TOO_LONG"), ("../data/file", "TRADE_ID_INVALID"), (r"C:\\data\\file", "TRADE_ID_INVALID")):
        route, _ = _compile_route({"trade_id": trade_id})
        payload, status = route()
        assert status == 400
        assert payload["error"] == error


def test_route_makes_no_network_broker_or_write_and_preserves_official_result(monkeypatch, tmp_path):
    route, _ = _compile_route({"trade_id": "TR-SAFE"})
    _install_validator(monkeypatch, _report("PASS"))
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    broker_before = sys.modules.get("broker")
    operational_result = {"ok": True, "status": "OFFICIAL_UNCHANGED"}
    files_before = list(tmp_path.iterdir())

    payload, status = route()

    assert status == 200 and payload["pass"] is True
    assert sys.modules.get("broker") is broker_before
    assert list(tmp_path.iterdir()) == files_before == []
    assert operational_result == {"ok": True, "status": "OFFICIAL_UNCHANGED"}


def test_route_contains_no_automatic_or_mutating_integration():
    source = ast.unparse(_route_function_node())
    forbidden = (
        "Thread(",
        ".start(",
        "schedule",
        "watchdog",
        "send_telegram",
        "central_broker",
        "register_open_trade",
        "update_trade(",
        "close_trade(",
        "open(",
        "write_text",
        "write_bytes",
    )
    assert all(item not in source for item in forbidden)
