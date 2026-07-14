from __future__ import annotations

import ast
import copy
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))


class Logger:
    def __init__(self):
        self.calls = []

    def exception(self, *args):
        self.calls.append(args)


def _node():
    return copy.deepcopy(next(item for item in TREE.body if isinstance(item, ast.FunctionDef) and item.name == "live_trade_snapshot_v1_route"))


def _route(args):
    node = _node()
    node.decorator_list = []
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    logger = Logger()
    namespace = {"request": SimpleNamespace(args=args), "app": SimpleNamespace(logger=logger), "datetime": datetime, "timezone": timezone}
    exec(compile(tree, "<isolated-snapshot-route>", "exec"), namespace)
    return namespace["live_trade_snapshot_v1_route"], logger


def _install(monkeypatch, result=None, error=None):
    calls = []

    def build(trade_id):
        calls.append(trade_id)
        if error:
            raise error
        return result or _report()

    monkeypatch.setitem(sys.modules, "live_trade_snapshot", SimpleNamespace(build_live_trade_snapshot=build))
    return calls


def _report(status="NOT_FOUND"):
    return {"ok": True, "snapshot_version": "LIVE_TRADE_SNAPSHOT_V1", "generated_at": "2026-07-14T00:00:00Z", "trade_id": "TR-1", "snapshot_status": status, "trade_status": "UNKNOWN", "fail_open": True, "production_blocked": False, "operational_impact": False, "identity": {}, "trade": {}, "broker": {}, "registry": {}, "lifecycle": {}, "execution": {}, "risk_protection": {}, "management": {}, "shadow": {}, "telegram": {}, "timeline_validation": {}, "external_exposure": {}, "component_status": {}, "divergences": [], "warnings": [], "errors": []}


def test_route_is_get_only():
    assert [ast.unparse(item) for item in _node().decorator_list] == ["app.route('/trade_snapshot', methods=['GET'])"]


def test_missing_and_empty_trade_id_return_400():
    for args in ({}, {"trade_id": "  "}):
        payload, status = _route(args)[0]()
        assert status == 400 and payload["error"] == "TRADE_ID_REQUIRED"


def test_trim_and_not_found_return_200(monkeypatch):
    route, _ = _route({"trade_id": "  TR-1  "})
    calls = _install(monkeypatch, _report("NOT_FOUND"))
    payload, status = route()
    assert status == 200 and payload["snapshot_status"] == "NOT_FOUND"
    assert calls == ["TR-1"]


def test_open_closed_and_divergent_are_http_200(monkeypatch):
    for snapshot_status in ("HEALTHY", "INCOMPLETE", "DIVERGENT", "DEGRADED"):
        route, _ = _route({"trade_id": "TR-1"})
        _install(monkeypatch, _report(snapshot_status))
        payload, status = route()
        assert status == 200 and payload["snapshot_status"] == snapshot_status


def test_invalid_length_path_null_and_controls_return_400():
    values = ("X" * 257, "../data", r"C:\data", "A\x00B", "A\nB")
    for value in values:
        payload, status = _route({"trade_id": value})[0]()
        assert status == 400


def test_unexpected_route_error_is_sanitized(monkeypatch):
    route, logger = _route({"trade_id": "TR-1"})
    _install(monkeypatch, error=RuntimeError("C:/secret/token"))
    payload, status = route()
    assert status == 500
    assert payload["errors"] == [{"code": "LIVE_TRADE_SNAPSHOT_ROUTE_INTERNAL_ERROR"}]
    assert "secret" not in str(payload)
    assert logger.calls


def test_extra_parameters_cannot_select_sources(monkeypatch):
    route, _ = _route({"trade_id": "TR-1", "source": "../../broker", "file": "secret"})
    calls = _install(monkeypatch)
    _, status = route()
    assert status == 200 and calls == ["TR-1"]


def test_route_has_no_mutating_or_automatic_behavior():
    source = ast.unparse(_node())
    forbidden = ("Thread(", ".start(", "schedule", "watchdog", "send_telegram", "place_market_order", "cancel_order", "close_trade(", "update_trade(", "open(", "write_text")
    assert all(item not in source for item in forbidden)


def test_route_makes_no_network_and_preserves_flags(monkeypatch):
    route, _ = _route({"trade_id": "TR-1"})
    _install(monkeypatch)
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    payload, status = route()
    assert status == 200
    assert payload["fail_open"] is True
    assert payload["production_blocked"] is False
    assert payload["operational_impact"] is False
